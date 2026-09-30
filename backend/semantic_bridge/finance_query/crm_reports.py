"""Read-only CRM reports using published field/relationship evidence.

No old catalog, fuzzy identity join or source writes. Source metadata was read on
2026-09-30. Missing historical/role evidence is a report gap, never a fabricated
business fact. Each relation is reduced to identity sets before counting.
"""
from collections import defaultdict, Counter
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import re
import unicodedata
from uuid import UUID
from zoneinfo import ZoneInfo

from .contracts import ContractError

REPORTS = {
    "book_quality": "Aktif kitapların ISBN/stok kodu/yayıncı/kişi yazar bağı/ilk baskı/son yayın/altmarka eksikleri; aynı kartta eksiklerin birlikte listesi ve yayıncı toplamları. start/end varsa CreatedOn aralığı.",
    "duplicate_isbn": "Boş olmayan aynı güncel ISBN kitap adayları; kimlik, ad, baskı sayısı/tarihleri ve yayıncı yan yana. Farklı eser/farklı baskı/olası mükerrer sınıfları hesaplanmaz; decision tüm adaylarda aynı uyarıdır, kimlik kanıtı değildir.",
    "duplicate_book_code": "Boş olmayan aynı stok kodu kitap adayları, ad/ISBN/baskı/yayıncı alanları yan yana. Farklı eser veya başka baskı sınıfları hesaplanmaz; decision tüm adaylarda aynı uyarıdır. Bilinmeyeni belirtmek desteklenir, kesin eser bağı çıkarılmaz.",
    "duplicate_title": "Aynı başlıklı kitap adaylarının yazar/ISBN/baskı/yayıncı alanları yan yana gösterilir. Farklı eserler ile olası mükerrerleri ayıran hesaplanmış sınıflandırma yok; tüm candidate satırlarında decision aynı genel uyarıdır. Alanların varlığı ayrımın yapılmış olduğu anlamına gelmez.",
    "title_variants": "Yalnız boşluk/noktalama/büyük-küçük harf farkıyla benzeşen başlık önerileri; kimlik eşleştirmesi değildir.",
    "author_link_gaps": "Yazar künye metni dolu, aktif Yazar rolünde aktif Contact bağlantısı olmayan kitaplar; kitap/yayıncı sayıları.",
    "author_text_mismatch": "Contact yazar adları ile kitap künye metninin birebir/normalize farkları; farklı kişiler otomatik birleşmez, müstear olasılığı açıklanır.",
    "duplicate_authors": "Aynı adlı aktif yazar kişileri ayrı kimliklerle, oluşturma/güncelleme ve bağlı kitap kimlikleriyle göster.",
    "multi_author_books": "Birden fazla benzersiz aktif Contact yazar bağı olan kitaplar; kitap bir kez, yazar sayısı ayrı.",
    "authors_without_books": "Aktif yazar Contact olup aktif kitap-Yazar rolü bağlantısı olmayan kişiler; ilişki yokluğu çalışma yokluğu değildir.",
    "publisher_author_coverage": "Yayıncı başına kitap ve benzersiz aktif kişi yazar sayısı, yayıncılar arası ortak kişiler; kimlikler korunur.",
    "subbrand_consistency": "İki gerçek alt marka alanını ayrı göster; kitap ayrıntısı ve yayıncı kimliği bazında eksik ana yayıncı toplamları. Altmarka→ana yayıncı bağı kanıtlanmadığından tutarsızlık hükmü gap.",
    "book_change_history": "Dönemde değişmiş kitaplar ve mevcut baskı/fiyat tarihçe kayıtları; genel eski-yeni alan ve yayıncı tarihçesi kanıtlanmadığında gap.",
    "author_contact_coverage": "Aktif kişi yazarların telefon/e-posta alanı doluluk göstergesi, yayıncı başına benzersiz kimlik sayımı; gerçek ulaşılabilirlik iddiası yok.",
    "duplicate_customer_tax": "Boş olmayan aynı vergi numarasındaki aktif müşteri kimlikleri ve aktif kişi bağlantıları; otomatik müşteri birleşmesi yok.",
    "customers_without_contacts": "Aktif müşteri kartlarına parent/primary/N:N ilişkileriyle bağlı aktif kişi yokluğu; son güncelleme sıralaması.",
    "contact_multiple_customers": "Aktif kişinin birden çok aktif müşteriyle kimlikli ilişkileri, ilişki yolu; hata hükmü yok.",
    "customer_geography": "Şehir ham/normalize dağılımı ve kayıtlı bölge; şehir-bölge referans uyumluluğu kanıtlanmadığında gap.",
    "publication_dates": "İlk Baskı Tarihi, Son Yayın Tarihi ve CreatedOn ayrı. Tüm kitap ayrıntısı yanında as_of itibarıyla tarihi gelmiş ve eksik alanı bulunan kitaplar her tarih türü için ayrı arrived_missing; tarih sırası sinyalleri ayrı chronology_signal. Tek yayın tarihi seçimi yapılmaz.",
    "catalog_additions": "start/end CreatedOn aralığında İstanbul ayı ve yayıncı bazında katalog kayıt eklenme sayısı; yayın tarihi değildir.",
    "editor_assignments": "Kitap Editor, Proje Editörü, yayın yönetmeni, sahip alanları ayrı ve kimlikli; kişi/rol başına kitap sayısı; atanamayanlar dahil.",
    "work_due": "Aktif iptal olmayan açık kitap iş planları, tahmini bitiş ve sorumlu/aşama eksikleri; geçmiş termin ve istenen gelecek dönem ayrı.",
    "work_due_missing": "İstenen gelecek dönem içindeki açık kitap işlerinden sorumlu veya aktif aşaması eksik olanları göster; geçmiş terminli tüm açık işleri overdue ile ayrıca ayır.",
    "contract_author_differences": "Kitap yazarlarıyla sözleşme Contact taraflarının kimlik kümeleri farklı olan kitap-sözleşmeleri göster. Account tarafı, eksik taraf/yazar veya karışık tür varsa karşılaştırılamadı satırı ve açık gap; isimden kimlik kurma.",
    "work_stage_history": "Aktif açık kitap iş planları ve mevcut aşama; aşamaya giriş tarihçesi kanıtlanmadığı için bekleme gününü uydurmadan gap.",
    "contract_expiry": "Aktif kitap-sözleşme bağlarında start/end aralığındaki sözleşme bitişi; boş bitiş ayrı. Yenileme/revize/fesih ayrı, otomatik satış yasağı yok.",
    "contract_overlap": "Aynı kitap sözleşmeleri tarih/hak/dil/bölge/ülke ham kayıt kesişim adayları; eksik kapsam/tarih kesin çakışma olmaz. Ülke ve bölge listelerinin birlikte AND/OR anlamı kanıtlanmadığından kapsam yorumu her zaman açık gap'tir; hukuki çakışma doğruluğu iddiası yok.",
    "contract_author_roles": "Sözleşme tarafı Contact/Account kimliği ve taraf tipi, kitap kişi-yazar bağlarından ayrı; yazar=hak sahibi varsayılmaz.",
    "contract_revision_evidence": "Aktif kitaplara bağlı aktif sözleşmelerin Ana Sözleşme Id metni ve UUID eşitlik kanıtı: boş/geçersiz/kendi kimliği/başka aktif kayıt/aktif karşılık yok. Başlangıç, bitiş, revize, yenileme, fesih ve doğrulanmış Ek Protokol tarih/bayrakları ayrı. Ana Id metni lookup değildir, soy ağacı veya hukuki öncelik kurulmaz; sözleşme logundaki PDF yolu alan değişiklik tarihçesi sayılmaz. Hukuki öncelik doğrulanmadığı için açık gap içerir.",
    "open_author_actions": "start/end döneminde randevusundan doğmuş hâlâ açık görevler; yazar randevu katılımcı kimliği ve task.new_randevuid üzerinden bağlanır. Serbest görüşme notlarında aynı işin tekrarını tarama/sınıflandırma yok; same_task_reference_count sabit1, not tekrar sayısı değildir. Boş görev bağı sonucu notlarda taahhüt veya tekrar yok demek değildir.",
    "appointments_with_actions": "start/end gelecek randevusu olan aktif yazarların önceki randevularından kalan açık görevleri; tekrarlanan iş kimliği çoğalmaz.",
    "publisher_completeness": "Yayıncı kitap sayısı ve ISBN/kişi-yazar bağı/ilk baskı/son yayın/altmarka doluluk yüzdeleri; tarih alanları ayrı.",
    "publisher_history": "Kitapta bugünkü yayıncı ile önceki yayıncı alanı ayrı; tarihsel geçerlilik aralığı bulunmadan eski satışlara geçmiş sınıflama atanamaz.",
}
CRM_REPORT_CAPABILITIES = {"reports": REPORTS, "rules": [
    "start dahil end hariç İstanbul takvim tarihi; as_of raporun referans tarihi. Model tarih üretirken parsedPeriods kullanır.",
    "Kitap kişinin yazarı: new_eserkatilim.new_Kitap + new_Katilimsaglayan(Contact) + rol adı Yazar. Account katılımcı kimliği Contact değildir.",
    "Genel yayın tarihi alanı kanıtlanmadı: ilk baskı ve son yayın ayrı. new_ilkyayintarihi ilk baskıdır.",
    "Raporlar salt CRM; satış/stok/tahsilat içermez. Gösterilen nüfus güncel aktiftir; geçmişte aktiflik yeniden kurulmaz.",
    "limit yalnız açık kullanıcı sınırı; aksi halde null. Gaps tam cevap kabulünü engeller."]}
CRM_REPORT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["kind", "report", "start", "end", "as_of", "limit"], "properties": {
    "kind": {"type": "string", "enum": ["crm_report"]}, "report": {"type": "string", "enum": list(REPORTS)},
    "start": {"anyOf": [{"type": "string"}, {"type": "null"}]}, "end": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    "as_of": {"type": "string"}, "limit": {"anyOf": [{"type": "integer", "minimum": 1, "maximum": 1000}, {"type": "null"}]}}}

# Output vocabulary follows Sources and the record builders below. These are
# capability descriptions, not projections: selecting a report does not remove
# any existing result field. Shared sets keep the planning prompt bounded.
_OUTPUT_FIELDSETS = {
    "book": "book_id book_code book_name isbn author_text publisher_id publisher subbrand_id subbrand alternate_subbrand_id alternate_subbrand first_print_date last_publication_date edition_count last_print_date created_at updated_at editor_id project_editor_id publishing_director_id owner_id previous_publisher_id book_project_id project_card_id author_count author_ids author_names".split(),
    "publisher": "publisher_id publisher book_count".split(),
    "person": "person_id person_name created_at updated_at book_count books publisher_ids has_email has_phone".split(),
    "customer": "customer_id customer_name tax_number territory_id territory primary_contact_id created_at updated_at city region country active_contact_count contacts".split(),
    "contract": "book_id book_name contract_id contract_number start_date end_date revised_end_date renewal_start_date renewal_end_date termination_date indefinite_flag rights languages regions countries parties author_people end_date_status".split(),
    "revision": "parent_contract_text protocol_date protocol_end_date is_addendum addendum_time_limited parent_contract_id parent_reference_status parent_contract_number parent_match_basis".split(),
    "work": "work_id work_name project_id owner_id stage_id due_date actual_end work_state cancelled created_at updated_at project_name stage_name books overdue missing_owner missing_stage".split(),
    "action": "person_id person_name task_id task_subject owner_id due_date".split(),
}


def _output_record(grain, *fieldsets, fields=""):
    return {"grain": grain, "fieldsets": list(fieldsets), "fields": fields.split()}


def _output_contracts():
    contracts = {}
    def add(names, records, dates="No date filtering; current active population.", gaps="No mandatory gap; source/identity checks still apply."):
        for name in names.split():
            contracts[name] = {"record_types": records, "date_semantics": dates, "gaps": gaps}
    bookdates = "Optional start/end selects book CreatedOn in Istanbul [start,end). Base book population is ordered CreatedOn then book_id; candidate grouping or summary/detail output can reorder records, so no arbitrary global result sort is implied. Does not select publication dates."
    quality = "multiple_core_missing_book_count " + " ".join(prefix+f for prefix in ("missing_", "filled_pct_") for f in ("isbn","book_code","publisher","author_link","first_print_date","last_publication_date","subbrand"))
    add("book_quality publisher_completeness", {
        "publisher_summary": _output_record("publisher_id", "publisher", fields=quality),
        "book_detail": _output_record("book_id with at least one missing field", "book", fields="missing_fields missing_count missing_core_fields core_missing_count record_age_days")}, bookdates+" record_age_days uses as_of minus CreatedOn local date.")
    add("duplicate_isbn duplicate_book_code duplicate_title title_variants", {
        "candidate": _output_record("book_id in matching-field candidate group", "book", fields="matching_field matching_value candidate_count decision")}, bookdates,
        "No mandatory runtime gap for this candidate report. Non-claims below describe prohibitions the report respects; they are not missing requested outputs.")
    for name in ("duplicate_isbn","duplicate_book_code","duplicate_title","title_variants"):
        contracts[name].update(
            supported={"candidate_listing": True, "raw_fields_side_by_side": True,
                       "comparison_fields": ["book_id","book_name","isbn","book_code","author_ids","author_names","author_text","edition_count","first_print_date","last_print_date","last_publication_date","publisher_id","publisher"],
                       "original_and_matching_key": True, "preserves_distinct_record_ids": True,
                       "uniform_candidate_caution": True},
            non_claims={"asserts_same_work": False, "definitive_duplicate": False,
                        "auto_merge": False, "work_identity_proven": False,
                        "meaning": "These false assertions fulfill 'do not assume/declare/merge' prohibitions. They do not require a gap or make a candidate-only comparison incomplete."},
            unsupported_requested_operations={"identity_partition": "not_computed",
                        "different_work_vs_possible_duplicate_classes": "not_computed",
                        "same_work_different_edition_verdict": "not_computed",
                        "applies_only_when": "User affirmatively requires this classification or verdict; not when the user prohibits asserting it.",
                        "review_action": "A mandatory uncomputed partition cannot be marked complete. Reject it or explicitly carry its unverified gap in a valid partial-answer plan. Raw side-by-side comparison alone does not compute a partition."})
    basic = {"book_detail": _output_record("book_id", "book"), "publisher_summary": _output_record("publisher_id among selected findings", "publisher")}
    add("author_link_gaps multi_author_books", basic, bookdates)
    add("author_text_mismatch", {**basic, "book_detail": _output_record("book_id", "book", fields="comparison")}, bookdates)
    contracts["author_text_mismatch"].update(
        supported={"raw_author_text_and_linked_contact_ids_side_by_side": True,
                   "comparison_fields": ["book_id","author_text","author_ids","author_names","comparison"],
                   "preserves_distinct_source_ids": True,
                   "normalized_text_comparison": "Single linked author: exact name equality excluded, normalized equality labelled spelling candidate. Multiple authors: exact normalized delimited-name set equality excluded; remaining differences remain candidates."},
        non_claims={"person_identity_merge": False, "auto_merge": False,
                    "name_similarity_proves_same_person": False,
                    "meaning": "Distinct Contact IDs remain distinct even when names match. Publisher counts group books, not person identities. A prohibition on merging people is respected and is not a missing operation."},
        unsupported_requested_operations={"resolve_pseudonym_or_person_identity_from_text": "not_computed"})
    add("duplicate_authors authors_without_books", {"person_detail": _output_record("active author Contact person_id", "person")})
    pubauthors = _output_record("publisher_id", "publisher", fields="author_count contact_field_present_count shared_author_ids")
    add("publisher_author_coverage", {"publisher_summary": pubauthors}, bookdates)
    add("author_contact_coverage", {"person_detail": _output_record("active author Contact person_id", "person"), "publisher_summary": pubauthors}, "Person details cover all active author Contacts and all active book links; optional start/end restricts only publisher summaries by book CreatedOn.")
    add("subbrand_consistency", {"book_detail": _output_record("book_id with alt-brand but unresolved active main publisher", "book", fields="finding"), "publisher_summary": _output_record("publisher_id among findings; null remains separate", "publisher")}, bookdates, "Always UNVERIFIED_DEFINITION: alt-brand to main publisher hierarchy unverified.")
    datesrecord = {"book_detail": _output_record("book_id", "book", fields="missing_fields created_after_first_print last_publication_before_first_print")}
    add("publication_dates", {**datesrecord,
        "arrived_missing": _output_record("book_id + date_basis with date<=as_of and missing metadata", "book", fields="missing_fields date_basis recorded_date"),
        "chronology_signal": _output_record("book_id with at least one chronology signal", "book", fields="missing_fields created_after_first_print last_publication_before_first_print")}, bookdates+" Separate arrived_missing rows compare first_print_date and last_publication_date independently to as_of; neither is silently chosen as a universal publication date.")
    add("publisher_history", datesrecord, bookdates, "Always UNVERIFIED_DEFINITION: previous publisher Account and current publisher Marka do not establish historical validity intervals.")
    add("catalog_additions", {"month_summary": _output_record("Istanbul creation month + publisher_id", "publisher", fields="created_month")}, "Required start/end selects book CreatedOn; created_month is Istanbul creation month, not publication month.")
    add("editor_assignments", {
        "assignment_detail": _output_record("book_id + role", fields="book_id book_name role person_id person_name user_disabled identity_status"),
        "assignment_summary": _output_record("role + person_id + person_name", fields="role person_id person_name book_count")}, bookdates)
    add("book_change_history", {
        "modified_book": _output_record("book_id", "book"),
        "history_snapshot": _output_record("history_id", fields="history_id book_id recorded_at edition_count vat_inclusive_price")}, "Required start/end selects book ModifiedOn; snapshots additionally require their CreatedOn in same range and book in modified-book set.", "Always UNVERIFIED_DEFINITION: price/print snapshots and ModifiedOn do not decode old/new changes or reasons.")
    add("duplicate_customer_tax customers_without_contacts", {"customer_detail": _output_record("customer_id; ordered updated_at oldest first", "customer")})
    add("contact_multiple_customers", {"relationship": _output_record("person_id + customer_id + relationship_type", fields="person_id person_name customer_id customer_name relationship_type customer_count decision")})
    add("customer_geography", {"city_distribution": _output_record("raw_city + normalized_city + region + territory_id", fields="raw_city normalized_city region territory_id record_count normalized_city_total")}, gaps="Always UNVERIFIED_DEFINITION: text normalization is not official city/region identity or hierarchy.")
    add("work_due", {"work_detail": _output_record("work_id", "work")}, "Required start/end: includes overdue due_date before as_of OR due_date in [start,end); overdue is independent of requested range.")
    add("work_due_missing", {"work_detail": _output_record("work_id", "work")}, "Required start/end: overdue due_date before as_of OR due_date in [start,end) AND missing_owner/missing_stage. Overdue rows include all open work regardless of missing fields.")
    add("work_stage_history", {"work_detail": _output_record("work_id", "work")}, "Current open plans; no period filter. as_of only determines overdue.", "Always UNVERIFIED_DEFINITION: stage entry/exit dates and days in stage unknown; ModifiedOn is not stage entry.")
    contractrecord = {"contract_detail": _output_record("book_id + contract_id", "contract")}
    precedence = "Relevant revised_end_date, renewal_end_date or termination_date adds UNVERIFIED_DEFINITION: no legal precedence/effective-end calculation."
    add("contract_expiry", contractrecord, "Required start/end: any main end, revised end, renewal end or termination in interval, OR main end missing. Start_date output is contract start, not filter start.", precedence)
    role_record={"contract_detail": _output_record("book_id + contract_id", "contract", fields="role_comparison author_only_ids party_only_ids")}
    add("contract_author_roles", contractrecord, gaps=precedence)
    add("contract_author_differences", role_record, gaps=precedence+" Only complete nonempty Contact sets compared: equal sets omitted, unequal sets retained. Any unresolved active author participation/role or contract party prevents comparison even if the visible subset matches. Account/mixed/missing identity sets retained as unverified with gap, never name-matched.")
    add("contract_revision_evidence", {"contract_detail": _output_record("book_id + contract_id", "contract", "revision")}, gaps="Always UNVERIFIED_DEFINITION: UUID text equality gives parent evidence only, not legal precedence or revision chronology. PDF log paths are not old/new history.")
    add("contract_overlap", {"contract_pair": _output_record("book_id + ordered contract_id/other_contract_id pair", fields="book_id book_name contract_id other_contract_id scope_status scope_intersections contract_start_date contract_end_date other_start_date other_end_date overlap_start_date overlap_end_date")}, "No period filter. Pairwise recorded main start/end dates inclusive; missing scope/dates remains an uncertain candidate.", "Always UNVERIFIED_DEFINITION scope_interpretation_unverified: country/region AND/OR and legal overlap unverified, even when no candidates. Additional missing-scope/precedence gaps possible.")
    add("open_author_actions", {"open_action": _output_record("person_id + task_id + meeting_id", "action", fields="meeting_id meeting_start same_task_reference_count")}, "Required start/end selects originating meeting ScheduledStart; task must still be open now, not as of historical date.",
        "Explicit linked-task listing is supported. No free-text meeting-note scan, cross-note semantic deduplication, or evidence that repeated notes refer to the same real-world work. A mandatory note-repeat classification needs an explicit unverified gap or rejection; do not claim completion from task IDs or the constant reference count. Empty linked-task output does not prove no commitments/repetitions in notes.")
    add("appointments_with_actions", {"appointment_preparation": _output_record("appointment_id + person_id + task_id", "action", fields="appointment_id appointment_start appointment_subject prior_meeting_id prior_meeting_start")}, "Required start/end selects upcoming open/scheduled appointment; linked open task originates from strictly earlier meeting. Ordered appointment start.")
    return contracts


CRM_REPORT_OUTPUT_CONTRACTS = {
    "fieldsets": _OUTPUT_FIELDSETS,
    "reports": _output_contracts(),
    "common": {
        "record_type": "Discriminates row grain; mixed row types are not additive. Returned columns are union of present row fields; absent cells are null.",
        "empty": {"record_type": "summary", "fields": ["record_type", "record_count", "report"], "record_count": 0},
        "dates": "Naive source datetimes interpreted as UTC; filters/group dates use Europe/Istanbul, start inclusive/end exclusive. Output datetimes retain source ISO representation.",
        "limits": "Explicit limit slices completed report rows; no per-group top-N or hidden projection. Unrequested filters/sorts/aggregations are not implied by available fields.",
        "field_meanings": {
            "decision": "For duplicate_isbn/duplicate_book_code/duplicate_title/title_variants candidate rows, the same caution is emitted for every candidate. It is NOT a per-record identity classification, comparison verdict or different-work-vs-duplicate partition.",
            "matching_field/matching_value/candidate_count": "Candidate group key and multiplicity only; neither shared key nor count establishes work/edition identity.",
            "same_task_reference_count": "Constant 1 for an explicit task-to-originating-meeting relation. Not computed repeated-note count, cross-meeting occurrence count, or common-work identity evidence.",
            "contact_field_present_count": "Distinct active people with a nonblank email OR phone/mobile field. Not a verified reachable-person count, deliverability measure, or per-channel total.",
            "isbn": "Current ISBN13, not old ISBN.", "first_print_date": "First print date", "last_publication_date": "Last publication date", "created_at": "CRM creation time", "updated_at": "CRM modification time, not field-specific history",
            "author_ids/author_names": "JSON arrays of distinct active Contact IDs/names through active Yazar participation; author_text is separate book imprint text.",
            "books": "JSON array of book_id/book_name objects", "contacts": "JSON array of person_id/person_name objects",
            "rights/languages/regions/countries": "JSON arrays of [id,name] scope pairs; absence does not mean unrestricted rights.",
            "parties": "JSON objects: party_id,contract_id,person_id,account_id,party_type_id,person_name,account_name,party_type; legal party role is separate from authorship.",
            "author_people": "JSON array person_id/person_name; book author link, not automatic rights holder.",
            "scope_intersections": "JSON object rights/languages/regions/countries with intersecting [id,name] pairs; candidate evidence only.",
            "overlap_start_date/overlap_end_date": "Intersection of recorded main contract dates in Istanbul days, inclusive; null if either date missing or intervals disjoint; not effective legal validity.",
            "role_comparison": "CONTACT_ID_SETS_EQUAL / CONTACT_ID_SETS_DIFFER / UNVERIFIED_IDENTITY_TYPES_OR_MISSING; compares only nonempty Contact sets, not legal ownership.",
            "author_only_ids/party_only_ids": "JSON Contact ID set differences when comparable; null for Account/mixed/missing identities.",
            "arrived_missing": "Same book may appear once per first_print_date/last_publication_date; date_basis identifies which recorded date arrived. Not additional unique books.",
            "region": "CustomerAddress StateOrProvince text; distinct from business TerritoryId/territory.",
            "parent_reference_status": "NOT_RECORDED / INVALID_UUID_TEXT / SELF_REFERENCE / OTHER_ACTIVE_RECORD / ACTIVE_PARENT_NOT_FOUND; no passive parent record loaded.",
            "missing_core_fields/core_missing_count": "Missing among isbn,book_code,publisher only; missing_fields/missing_count also include dates,subbrand,author_link.",
            "filled_pct_*": "Percent of publisher books with field/active author link present, not external validity verification.",
            "has_email/has_phone": "Field present boolean; actual address/number not in person_detail and reachability not proven.",
        },
    },
}
CRM_REPORT_CAPABILITIES["output_contracts"] = CRM_REPORT_OUTPUT_CONTRACTS


def describe_crm_report_output(report):
    """Expand only the selected report for semantic review; no source values."""
    contract = CRM_REPORT_OUTPUT_CONTRACTS["reports"].get(report)
    if contract is None:
        raise ContractError("Bilinmeyen CRM rapor çıktı sözleşmesi.", code="PLAN_INVALID")
    records = {}
    for kind, spec in contract["record_types"].items():
        fields = ["record_type"]
        for name in spec["fieldsets"]: fields.extend(_OUTPUT_FIELDSETS[name])
        fields.extend(spec["fields"])
        records[kind] = {"grain": spec["grain"], "fields": list(dict.fromkeys(fields))}
    return {"report": report, "description": REPORTS[report], "record_types": records,
            "date_semantics": contract["date_semantics"], "gaps": contract["gaps"],
            "common": CRM_REPORT_OUTPUT_CONTRACTS["common"],
            **{key:contract[key] for key in ("supported","non_claims","unsupported_requested_operations") if key in contract}}


def validate_crm_report(raw):
    if not isinstance(raw, dict) or set(raw) != set(CRM_REPORT_SCHEMA["properties"]) or raw.get("kind") != "crm_report" or raw.get("report") not in REPORTS:
        raise ContractError("CRM rapor planı kapalı sözleşmeyle uyuşmuyor.", code="PLAN_INVALID")
    for k in ("start", "end", "as_of"):
        if raw[k] is None and k != "as_of": continue
        try:
            if not isinstance(raw[k], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw[k]): raise ValueError()
            date.fromisoformat(raw[k])
        except (ValueError, TypeError): raise ContractError("CRM rapor tarihi ISO gün olmalı.", code="PLAN_INVALID") from None
    if (raw["start"] is None) != (raw["end"] is None) or raw["start"] and raw["start"] >= raw["end"]:
        raise ContractError("CRM rapor aralığı başlangıç/bitiş gerektirir.", code="PLAN_INVALID")
    if raw["limit"] is not None and (type(raw["limit"]) is not int or not 1 <= raw["limit"] <= 1000):
        raise ContractError("CRM rapor sınırı geçersiz.", code="PLAN_INVALID")
    if raw["report"] in {"catalog_additions", "contract_expiry", "open_author_actions", "appointments_with_actions", "book_change_history", "work_due", "work_due_missing"} and not raw["start"]:
        raise ContractError("CRM raporu için tarih aralığı gerekli.", code="NEEDS_CLARIFICATION")
    return dict(raw)


def _key(v): return str(v).strip().lower() if v is not None else None
def _text(v): return str(v).strip() if v is not None and str(v).strip() else None
def _norm(v):
    s = str(v or "").translate(str.maketrans({"I": "ı", "İ": "i"})).casefold()
    return "".join(c for c in unicodedata.normalize("NFKC", s) if c.isalnum())
def _json(v): return json.dumps(v, ensure_ascii=False, default=str, sort_keys=True)
def _day(v):
    if not v: return None
    if isinstance(v, date) and not isinstance(v, datetime): return v
    d = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(ZoneInfo("Europe/Istanbul")).date()
def _within(v, p): return bool(v) and (not p["start"] or p["start"] <= str(_day(v)) < p["end"])
def _wire(v):
    if isinstance(v, (datetime, date)): return v.isoformat()
    if isinstance(v, UUID): return str(v)
    if isinstance(v, Decimal): return float(v)
    return v


class Sources:
    def __init__(self, ex): self.ex, self.cache = ex, {}
    def rows(self, table, fields, where="r.statecode=0"):
        from .executor import CRM
        self.ex.verify_schema({table: list(fields.values()) + (["statecode"] if "r.statecode" in where else [])}, "crm")
        sql = "SELECT " + ",".join(f"r.[{col}] AS [{name}]" for name, col in fields.items()) + f" FROM {CRM}.[{table}] r WHERE {where}"
        return [{k: _wire(v) for k, v in r.items()} for r in self.ex.read(sql, source="crm")]
    def keyed(self, rows, key):
        out = {}
        for row in rows:
            k = _key(row[key])
            if k in out: raise ContractError("CRM kaynak kimliği tekil değil: " + key, code="SOURCE_CONTRACT_VIOLATION")
            out[k] = row
        return out
    def books(self):
        if "books" in self.cache: return self.cache["books"]
        books = self.rows("new_kitapBase", {"book_id":"new_kitapId", "book_code":"new_stokkodu", "book_name":"new_name", "isbn":"new_isbn13", "author_text":"new_yazartext", "publisher_id":"new_yayineviid", "subbrand_id":"new_yayinciid", "alternate_subbrand_id":"new_YayneviAltMarka", "first_print_date":"new_ilkyayintarihi", "last_publication_date":"new_sonyayintarihi", "edition_count":"new_baskisayisi", "last_print_date":"new_baskitarihi", "created_at":"CreatedOn", "updated_at":"ModifiedOn", "editor_id":"new_Editor", "project_editor_id":"new_projeeditoru", "publishing_director_id":"new_yayinyonetmeni", "owner_id":"OwnerId", "previous_publisher_id":"new_oncekiyayineviid", "book_project_id":"new_KitapProjesi", "project_card_id":"new_projekarti"}, self.ex.crm_status("new_kitapBase", "r"))
        publishers = self.keyed(self.rows("new_markaBase", {"publisher_id":"new_markaId", "publisher":"new_name"}, self.ex.crm_status("new_markaBase", "r")), "publisher_id")
        brands = self.keyed(self.rows("new_yaynevialtmarkaBase", {"id":"new_yaynevialtmarkaId", "name":"new_name"}), "id")
        for b in books:
            b["publisher"] = publishers.get(_key(b["publisher_id"]), {}).get("publisher")
            b["subbrand"] = publishers.get(_key(b["subbrand_id"]), {}).get("publisher")
            b["alternate_subbrand"] = brands.get(_key(b["alternate_subbrand_id"]), {}).get("name")
        self.cache["books"] = self.keyed(books, "book_id")
        return self.cache["books"]
    def people(self):
        if "people" not in self.cache:
            self.cache["people"] = self.keyed(self.rows("ContactBase", {"person_id":"ContactId", "person_name":"FullName", "is_author":"new_yazarmi", "email":"EMailAddress1", "phone":"Telephone1", "mobile":"MobilePhone", "created_at":"CreatedOn", "updated_at":"ModifiedOn", "parent_id":"ParentCustomerId", "parent_type":"ParentCustomerIdType"}, self.ex.crm_status("ContactBase", "r")), "person_id")
        return self.cache["people"]
    def author_links(self):
        if "links" in self.cache: return self.cache["links"]
        role_records = self.keyed(self.rows("new_katilimcitipiBase", {"id":"new_katilimcitipiId", "name":"new_name"}), "id")
        roles = {k for k, r in role_records.items() if _norm(r["name"]) == "yazar"}
        if not roles: raise ContractError("CRM katılım tipi sözlüğünde aktif Yazar rolü bulunamadı.", code="SOURCE_CONTRACT_VIOLATION")
        books, people = self.books(), self.people()
        links = self.rows("new_eserkatilimBase", {"link_id":"new_eserkatilimId", "book_id":"new_Kitap", "person_id":"new_Katilimsaglayan", "role_id":"new_katilimciTipi"})
        bybook = defaultdict(set)
        incomplete=set()
        for r in links:
            bid, pid = _key(r["book_id"]), _key(r["person_id"])
            role=_key(r["role_id"])
            if bid in books and (role not in role_records or not _text(role_records[role]["name"]) or (role in roles and pid not in people)):
                incomplete.add(bid)
            if bid in books and pid in people and role in roles: bybook[bid].add(pid)
        self.cache["author_link_incomplete"] = incomplete
        self.cache["links"] = bybook
        return bybook
    def customers(self):
        if "customers" not in self.cache:
            customers = self.keyed(self.rows("AccountBase", {"customer_id":"AccountId", "customer_name":"Name", "tax_number":"new_VergiNo", "territory_id":"TerritoryId", "primary_contact_id":"PrimaryContactId", "created_at":"CreatedOn", "updated_at":"ModifiedOn"}, self.ex.crm_status("AccountBase", "r")), "customer_id")
            # Dynamics exposes Address1_* virtual fields on Account, but their
            # physical storage is CustomerAddressBase (verified live inventory).
            from .executor import CRM
            addresses = self.keyed(self.rows("CustomerAddressBase", {"customer_id":"ParentId", "city":"City", "region":"StateOrProvince", "country":"Country"},
                "r.ObjectTypeCode=1 AND r.AddressNumber=1 AND EXISTS (SELECT 1 FROM " + CRM + ".AccountBase c WHERE c.AccountId=r.ParentId AND " + self.ex.crm_status("AccountBase","c") + ")"), "customer_id")
            territories = self.keyed(self.rows("TerritoryBase", {"territory_id":"TerritoryId", "territory":"Name"}, "1=1"), "territory_id")
            for cid,c in customers.items():
                c.update(city=addresses.get(cid,{}).get("city"), region=addresses.get(cid,{}).get("region"), country=addresses.get(cid,{}).get("country"), territory=territories.get(_key(c["territory_id"]),{}).get("territory"))
            self.cache["customers"] = customers
        return self.cache["customers"]
    def customer_links(self):
        people, customers = self.people(), self.customers()
        links = set()
        for pid, p in people.items():
            if p["parent_type"] == 1 and _key(p["parent_id"]) in customers: links.add((pid, _key(p["parent_id"]), "Contact.ParentCustomerId"))
        for cid, c in customers.items():
            if _key(c["primary_contact_id"]) in people: links.add((_key(c["primary_contact_id"]), cid, "Account.PrimaryContactId"))
        for r in self.rows("new_contact_accountBase", {"person_id":"contactid", "customer_id":"accountid"}, "1=1"):
            if _key(r["person_id"]) in people and _key(r["customer_id"]) in customers: links.add((_key(r["person_id"]), _key(r["customer_id"]), "new_contact_account"))
        return sorted(links)


def _gap(out, reason, status="UNVERIFIED_DEFINITION"):
    out["gaps"].append({"status": status, "reason": reason})
    out["notes"].append(reason)


def _book_reports(s, p, out):
    report, books, links, people = p["report"], s.books(), s.author_links(), s.people()
    selected = sorted((b for b in books.values() if not p["start"] or _within(b["created_at"], p)),
                      key=lambda b:(str(b["created_at"] or ""),str(b["book_id"])))
    bypub = defaultdict(list)
    for b in selected: bypub[_key(b["publisher_id"])].append(b)
    def detail(b):
        ids = sorted(links.get(_key(b["book_id"]), set()))
        return {**b, "author_count": len(ids), "author_ids": _json(ids), "author_names": _json([people[i]["person_name"] for i in ids])}
    def missing(b):
        fields = [f for f in ("isbn", "book_code", "publisher", "first_print_date", "last_publication_date", "subbrand") if not _text(b[f])]
        if not links.get(_key(b["book_id"])): fields.append("author_link")
        return fields
    rows = out["records"]
    if report in {"book_quality", "publisher_completeness"}:
        for pub, group in bypub.items():
            counts = Counter(f for b in group for f in missing(b))
            rows.append({"record_type":"publisher_summary", "publisher_id": pub, "publisher":group[0]["publisher"], "book_count": len(group), "multiple_core_missing_book_count":sum(sum(f in missing(b) for f in ("isbn","book_code","publisher"))>1 for b in group), **{"missing_"+f: counts[f] for f in ("isbn","book_code","publisher","author_link","first_print_date","last_publication_date","subbrand")}, **{"filled_pct_"+f: 100*(len(group)-counts[f])/len(group) for f in ("isbn","book_code","publisher","author_link","first_print_date","last_publication_date","subbrand")}})
        for b in selected:
            m = missing(b)
            core=[f for f in m if f in ("isbn","book_code","publisher")]
            if m: rows.append({"record_type":"book_detail", **detail(b), "missing_fields":_json(m), "missing_count":len(m), "missing_core_fields":_json(core),"core_missing_count":len(core), "record_age_days":(date.fromisoformat(p["as_of"])-_day(b["created_at"])).days if b["created_at"] else None})
        out["notes"].append("İlk baskı ve son yayın tarihleri ayrı doluluk ölçüsüdür; tek bir yayın tarihi varsayılmadı.")
    elif report in {"duplicate_isbn", "duplicate_book_code", "duplicate_title", "title_variants"}:
        field = {"duplicate_isbn":"isbn", "duplicate_book_code":"book_code", "duplicate_title":"book_name", "title_variants":"book_name"}[report]
        grouped = defaultdict(list)
        for b in selected:
            value = _text(b[field])
            if value: grouped[_norm(value) if report=="title_variants" else value.casefold()].append(b)
        for key, group in sorted(grouped.items()):
            if len(group)<2: continue
            if report=="title_variants" and len({b[field] for b in group})<2: continue
            for b in group: rows.append({"record_type":"candidate", **detail(b), "matching_field":field, "matching_value":key, "candidate_count":len(group), "decision":"İncelenecek aday; baskı/eser/kişi kimliği otomatik birleştirilmedi"})
    elif report in {"author_link_gaps", "author_text_mismatch", "multi_author_books"}:
        chosen=[]
        for b in selected:
            r=detail(b); names=[people[i]["person_name"] for i in sorted(links.get(_key(b["book_id"]),set()))]
            if report=="author_link_gaps" and _text(b["author_text"]) and not names: chosen.append(r)
            elif report=="multi_author_books" and len(names)>1: chosen.append(r)
            elif report=="author_text_mismatch" and names:
                text=_text(b["author_text"])
                if len(names)==1 and text==names[0]: continue
                if len(names)>1:
                    # Exact delimited names only; substring similarity is not
                    # proof that a different person is the same author.
                    tokens={_norm(x) for x in re.split(r"[;,/]|\s+ve\s+",text or "",flags=re.IGNORECASE) if _text(x)}
                    if tokens=={_norm(n) for n in names}: continue
                r["comparison"]="Yazım farkı adayı" if len(names)==1 and _norm(text)==_norm(names[0]) else "Künye/kişi farkı; müstear veya çoklu yazarlık ayrıca incelenmeli"
                chosen.append(r)
        for r in chosen: rows.append({"record_type":"book_detail", **r})
        counts=Counter((_key(r["publisher_id"]),r["publisher"]) for r in chosen)
        rows.extend({"record_type":"publisher_summary", "publisher_id":k[0], "publisher":k[1], "book_count":n} for k,n in counts.items())
    elif report in {"duplicate_authors", "authors_without_books", "author_contact_coverage", "publisher_author_coverage"}:
        byperson=defaultdict(set)
        for bid,pids in links.items():
            for pid in pids: byperson[pid].add(bid)
        authors={pid:r for pid,r in people.items() if r["is_author"]}
        same=Counter((_text(r["person_name"]) or "").casefold() for r in authors.values())
        for pid,r in authors.items():
            if report=="duplicate_authors" and (not _text(r["person_name"]) or same[_text(r["person_name"]).casefold()]<2): continue
            if report=="authors_without_books" and byperson[pid]: continue
            if report=="publisher_author_coverage": continue
            ids=sorted(byperson[pid]); pubs={_key(books[bid]["publisher_id"]) for bid in ids}
            rows.append({"record_type":"person_detail", "person_id":r["person_id"], "person_name":r["person_name"], "created_at":r["created_at"], "updated_at":r["updated_at"], "book_count":len(ids), "books":_json([{"book_id":bid,"book_name":books[bid]["book_name"]} for bid in ids]), "publisher_ids":_json(sorted(pubs,key=str)), "has_email":bool(_text(r["email"])), "has_phone":bool(_text(r["phone"]) or _text(r["mobile"]))})
        if report in {"publisher_author_coverage","author_contact_coverage"}:
            pubpeople={pub:set().union(*(links.get(_key(b["book_id"]),set()) for b in group)) for pub,group in bypub.items()}
            if report=="author_contact_coverage": pubpeople={pub:pids & set(authors) for pub,pids in pubpeople.items()}
            for pub,group in bypub.items():
                pids=pubpeople[pub]
                rows.append({"record_type":"publisher_summary", "publisher_id":pub, "publisher":group[0]["publisher"], "book_count":len(group), "author_count":len(pids), "contact_field_present_count":sum(bool(_text(people[i]["email"]) or _text(people[i]["phone"]) or _text(people[i]["mobile"])) for i in pids), "shared_author_ids":_json(sorted(i for i in pids if sum(i in ps for ps in pubpeople.values())>1))})
        out["notes"].append("İlişki yokluğu çalışılmadığı anlamına gelmez; iletişim alanının doluluğu gerçek ulaşılabilirlik garantisi değildir.")
    elif report=="subbrand_consistency":
        for b in selected:
            if (b["subbrand_id"] or b["alternate_subbrand_id"]) and not b["publisher"]: rows.append({"record_type":"book_detail", **detail(b), "finding":"Alt marka atanmış, aktif ana yayıncı çözülemedi"})
        counts=Counter((_key(r["publisher_id"]),r["publisher"]) for r in rows)
        rows.extend({"record_type":"publisher_summary","publisher_id":key[0],"publisher":key[1],"book_count":count} for key,count in counts.items())
        _gap(out,"İki alt marka alanı ayrı varlıklardır; yayımlı şemada bu alanlardan ana yayıncıya doğrulanmış ilişki bulunmadığından ilişki tutarlılığı kesin değerlendirilemedi.")
    elif report in {"publication_dates","catalog_additions","publisher_history"}:
        if report=="catalog_additions":
            counts=Counter((str(_day(b["created_at"]))[:7],_key(b["publisher_id"]),b["publisher"]) for b in selected if b["created_at"])
            rows.extend({"record_type":"month_summary","created_month":k[0],"publisher_id":k[1],"publisher":k[2],"book_count":v} for k,v in sorted(counts.items(),key=str))
            out["notes"].append("Aylar İstanbul takviminde kayıt oluşturma tarihidir; kitap yayın ayı değildir.")
        else:
            for b in selected:
                m=missing(b)
                row={"record_type":"book_detail",**detail(b),"missing_fields":_json(m), "created_after_first_print":bool(b["created_at"] and b["first_print_date"] and _day(b["created_at"])>_day(b["first_print_date"])), "last_publication_before_first_print":bool(b["last_publication_date"] and b["first_print_date"] and _day(b["last_publication_date"])<_day(b["first_print_date"]))}
                rows.append(row)
                if report=="publication_dates":
                    if row["created_after_first_print"] or row["last_publication_before_first_print"]:
                        rows.append({**row,"record_type":"chronology_signal"})
                    for basis in ("first_print_date","last_publication_date"):
                        if m and b[basis] and str(_day(b[basis]))<=p["as_of"]:
                            rows.append({"record_type":"arrived_missing",**detail(b),"missing_fields":_json(m),"date_basis":basis,"recorded_date":b[basis]})
            if report=="publisher_history": _gap(out,"Önceki yayıncı alanı Account, bugünkü yayıncı Marka varlığıdır; tarihsel geçerlilik aralığı kanıtlanmadı. Geçmiş satış için güncel sınıflama kullanıldığı açıkça belirtilmelidir.")
            else: out["notes"].append("Tarih sırası inceleme sinyalidir; ilk baskıdan sonra CRM kaydı açılması tek başına hata değildir.")
    elif report=="editor_assignments":
        users=s.keyed(s.rows("SystemUserBase",{"user_id":"SystemUserId","user_name":"FullName","is_disabled":"IsDisabled"},"1=1"),"user_id")
        counts=Counter()
        for b in selected:
            for role in ("editor_id","project_editor_id","publishing_director_id","owner_id"):
                ident=_key(b[role]); u=users.get(ident,{})
                rows.append({"record_type":"assignment_detail","book_id":b["book_id"],"book_name":b["book_name"],"role":role,"person_id":ident,"person_name":u.get("user_name"),"user_disabled":u.get("is_disabled"),"identity_status":"Atanmamış" if not ident else "Kullanıcı" if u else "Takım/çözülemeyen sahip; kişi varsayılmadı"})
                counts[(role,ident,u.get("user_name"))]+=1
        rows.extend({"record_type":"assignment_summary","role":k[0],"person_id":k[1],"person_name":k[2],"book_count":v} for k,v in counts.items())
    elif report=="book_change_history":
        changed={bid:b for bid,b in books.items() if _within(b["updated_at"],p)}
        rows.extend({"record_type":"modified_book",**detail(b)} for b in changed.values())
        history=s.rows("new_kitapgecmisiBase",{"history_id":"new_kitapgecmisiId","book_id":"new_kitapid","recorded_at":"CreatedOn","edition_count":"new_baskisayisi","vat_inclusive_price":"new_kdvdahilfiyat"})
        rows.extend({"record_type":"history_snapshot",**r} for r in history if _key(r["book_id"]) in changed and _within(r["recorded_at"],p))
        _gap(out,"Kitap Geçmişi baskı/fiyat anlık kayıtları sunar; bütün alanların eski-yeni değer çifti veya değişiklik nedeni değildir. ModifiedOn'dan alan değişikliği çıkarılmadı.")


def _customer_reports(s,p,out):
    report, customers, people=p["report"],s.customers(),s.people()
    links=s.customer_links(); bycustomer=defaultdict(set); byperson=defaultdict(set)
    for pid,cid,role in links: bycustomer[cid].add(pid); byperson[pid].add(cid)
    rows=out["records"]
    if report=="contact_multiple_customers":
        for pid,cid,role in links:
            if len(byperson[pid])>1: rows.append({"record_type":"relationship","person_id":pid,"person_name":people[pid]["person_name"],"customer_id":cid,"customer_name":customers[cid]["customer_name"],"relationship_type":role,"customer_count":len(byperson[pid]),"decision":"Kaynakta ilişki var; hata olduğu çıkarılmadı"})
    elif report=="customer_geography":
        counts=Counter((_text(c["city"]),_norm(c["city"]),_text(c["region"]),_key(c["territory_id"])) for c in customers.values())
        normcount=Counter(_norm(c["city"]) for c in customers.values())
        rows.extend({"record_type":"city_distribution","raw_city":k[0],"normalized_city":k[1],"region":k[2],"territory_id":k[3],"record_count":n,"normalized_city_total":normcount[k[1]]} for k,n in counts.items())
        _gap(out,"Normalizasyon yalnız boşluk/noktalama/harf farkı önerisidir. Resmî şehir-bölge eşleme kanıtı yok; bölge tutarlılığı veya farklı şehir kimliği otomatik birleştirilmedi.")
    else:
        taxcounts=Counter(_text(c["tax_number"]) for c in customers.values() if _text(c["tax_number"]))
        chosen=sorted(customers.items(),key=lambda kv:str(kv[1]["updated_at"] or ""))
        for cid,c in chosen:
            if report=="customers_without_contacts" and bycustomer[cid]: continue
            if report=="duplicate_customer_tax" and (not _text(c["tax_number"]) or taxcounts[_text(c["tax_number"]) ]<2): continue
            rows.append({"record_type":"customer_detail",**c,"active_contact_count":len(bycustomer[cid]),"contacts":_json([{"person_id":pid,"person_name":people[pid]["person_name"]} for pid in sorted(bycustomer[cid])])})


def _contract_reports(s,p,out):
    if p["report"]=="contract_overlap":
        _gap(out,"Kapsam yorumu doğrulanamadı (scope_interpretation_unverified): sözleşmedeki ülke ve bölge listelerinin birlikte AND/OR anlamı veya ülke-bölge hiyerarşisi kanıtlanmadı. Gösterilenler ham kayıt kesişim adaylarıdır; kesin hak çakışması ya da çakışma yokluğu değildir.")
    books=s.books(); people=s.people(); links=s.author_links()
    contracts=s.keyed(s.rows("new_sozlesmeBase",{"contract_id":"new_sozlesmeId","contract_number":"new_name","start_date":"new_SozlesmeBaslangicTarihi","end_date":"new_SozlesmeBitisTarihi","revised_end_date":"new_revizebitistarihi","renewal_start_date":"new_yenilemebaslangictarihi","renewal_end_date":"new_yenilemebitistarihi","termination_date":"new_fesihtarihi","indefinite_flag":"new_suresizsozlesme"}),"contract_id")
    revision_fields={}
    if p["report"]=="contract_revision_evidence":
        revision_fields=s.keyed(s.rows("new_sozlesmeBase",{"contract_id":"new_sozlesmeId","parent_contract_text":"new_anasozlesmeid","protocol_date":"new_ekprotokoltarihi","protocol_end_date":"new_ekprotokolbitist","is_addendum":"new_EkProtokolyeni","addendum_time_limited":"new_ekprotokolsurelimi"}),"contract_id")
        for cid,r in revision_fields.items():
            raw=_text(r["parent_contract_text"]);parent=None
            if raw is None:status="NOT_RECORDED"
            else:
                try:parent=str(UUID(raw))
                except ValueError:status="INVALID_UUID_TEXT"
                else:status="SELF_REFERENCE" if parent==cid else "OTHER_ACTIVE_RECORD" if parent in contracts else "ACTIVE_PARENT_NOT_FOUND"
            r.update(parent_contract_id=parent,parent_reference_status=status,
                     parent_contract_number=contracts.get(parent,{}).get("contract_number"),
                     parent_match_basis="UUID metin eşitliği; yayımlı lookup/ebeveyn önceliği değildir")
        _gap(out,"Sözleşme revizyon kanıtı kayıtlı alanları gösterir; Ana Sözleşme Id lookup olmayan metindir. Öz referans, aktif karşılığı bulunamayan UUID veya ek protokol bayrağı hukuki geçerlilik/öncelik belirlemez. Revize, yenileme, fesih ve protokol tarihlerinin yürürlük önceliği doğrulanmadı; PDF yolları alan değişikliği tarihçesi sayılmadı.")
    bybook=defaultdict(set)
    for r in s.rows("new_new_sozlesme_new_kitapBase",{"contract_id":"new_sozlesmeid","book_id":"new_kitapid"},"1=1"):
        if _key(r["contract_id"]) in contracts and _key(r["book_id"]) in books: bybook[_key(r["book_id"])].add(_key(r["contract_id"]))
    scopes={}
    for name,table,col,target,targetid in [("rights","new_new_hak_new_sozlesmeBase","new_hakid","new_hakBase","new_hakId"),("languages","new_new_sozlesme_new_dilBase","new_dilid","new_dilBase","new_dilId"),("regions","new_new_sozlesme_new_blgeBase","new_blgeid","new_blgeBase","new_blgeId"),("countries","new_new_sozlesme_new_ulkeBase","new_ulkeid","new_ulkeBase","new_ulkeId")]:
        labels=s.keyed(s.rows(target,{"id":targetid,"name":"new_name"}),"id"); values=defaultdict(set)
        for r in s.rows(table,{"contract_id":"new_sozlesmeid","scope_id":col},"1=1"):
            if _key(r["scope_id"]) in labels: values[_key(r["contract_id"])].add((_key(r["scope_id"]),labels[_key(r["scope_id"])]["name"]))
        scopes[name]=values
    parties=defaultdict(list)
    incomplete_parties=set()
    partyrows=s.rows("new_sozlesmetarafiBase",{"party_id":"new_sozlesmetarafiId","contract_id":"new_sozlesmeid","person_id":"new_kisi","account_id":"new_Firma","party_type_id":"new_TarafTipi"})
    types=s.keyed(s.rows("new_sozlesmetaraftipiBase",{"id":"new_sozlesmetaraftipiId","name":"new_name"}),"id")
    accounts=s.keyed(s.rows("AccountBase",{"account_id":"AccountId","account_name":"Name"},"r.statecode=0"),"account_id")
    for r in partyrows:
        pid,aid=_key(r["person_id"]),_key(r["account_id"])
        if (pid and pid not in people) or (aid and aid not in accounts):
            incomplete_parties.add(_key(r["contract_id"]))
            continue
        parties[_key(r["contract_id"])].append({**r,"person_name":people.get(pid,{}).get("person_name"),"account_name":accounts.get(aid,{}).get("account_name"),"party_type":types.get(_key(r["party_type_id"]),{}).get("name")})
    rows=out["records"]
    for bid,cids in sorted(bybook.items()):
        b=books[bid]
        if p["report"]=="contract_overlap":
            ids=sorted(cids)
            for index,cid in enumerate(ids):
                a=contracts[cid]
                for other in ids[index+1:]:
                    z=contracts[other]
                    known=all(a[f] and z[f] for f in ("start_date","end_date")) and all(scopes[n][cid] and scopes[n][other] for n in ("rights","languages")) and bool((scopes["regions"][cid] and scopes["regions"][other]) or (scopes["countries"][cid] and scopes["countries"][other]))
                    timeover=known and _day(a["start_date"])<=_day(z["end_date"]) and _day(z["start_date"])<=_day(a["end_date"])
                    intersections={n:set(scopes[n][cid]) & set(scopes[n][other]) for n in scopes}
                    spatial_overlap=bool(intersections["regions"] or intersections["countries"])
                    if known and not (timeover and intersections["rights"] and intersections["languages"] and spatial_overlap): continue
                    dates_known=all(a[f] and z[f] for f in ("start_date","end_date"))
                    overlap_start=max(_day(a["start_date"]),_day(z["start_date"])) if dates_known else None
                    overlap_end=min(_day(a["end_date"]),_day(z["end_date"])) if dates_known else None
                    valid_interval=dates_known and overlap_start<=overlap_end
                    rows.append({"record_type":"contract_pair","book_id":bid,"book_name":b["book_name"],"contract_id":cid,"other_contract_id":other,"scope_status":"Tarih ve kayıtlı hak/dil/bölge kesişim adayı" if known else "DOĞRULANAMADI: tarih veya kapsam eksik", "scope_intersections":_json({n:sorted(v) for n,v in intersections.items()}),
                        "contract_start_date":a["start_date"],"contract_end_date":a["end_date"],"other_start_date":z["start_date"],"other_end_date":z["end_date"],
                        "overlap_start_date":str(overlap_start) if valid_interval else None,"overlap_end_date":str(overlap_end) if valid_interval else None})
                    if not known: _gap(out,"Bazı sözleşme çiftlerinde tarih/hak/dil/bölge eksik; eksik kapsam sınırsız kabul edilmedi.")
        else:
            for cid in sorted(cids):
                c=contracts[cid]
                if p["report"]=="contract_expiry" and c["end_date"] and not any(_within(c[f],p) for f in ("end_date","revised_end_date","renewal_end_date","termination_date")): continue
                comparison={}
                if p["report"]=="contract_author_differences":
                    authors=set(links.get(bid,set())); party_people={_key(r["person_id"]) for r in parties[cid] if r["person_id"]}
                    complete=bid not in s.cache["author_link_incomplete"] and cid not in incomplete_parties
                    comparable=complete and bool(authors and parties[cid]) and all(r["person_id"] and not r["account_id"] for r in parties[cid])
                    status=("CONTACT_ID_SETS_EQUAL" if authors==party_people else "CONTACT_ID_SETS_DIFFER") if comparable else "UNVERIFIED_IDENTITY_TYPES_OR_MISSING"
                    if not comparable: _gap(out,"Sözleşme tarafı-yazar karşılaştırması: kurum/karışık kimlik, çözülemeyen aktif katılım rolü veya eksik/çözülemeyen aktif kişi bağı nedeniyle Contact kimlik kümelerinin tamlığı kanıtlanamadı; isimden kişi/kurum eşleşmesi yapılmadı.")
                    if p["report"]=="contract_author_differences" and status=="CONTACT_ID_SETS_EQUAL": continue
                    comparison={"role_comparison":status,"author_only_ids":_json(sorted(authors-party_people)) if comparable else None,"party_only_ids":_json(sorted(party_people-authors)) if comparable else None}
                rows.append({"record_type":"contract_detail", **comparison, "book_id":bid,"book_name":b["book_name"], **c, **revision_fields.get(cid,{}), **{n:_json(sorted(scopes[n][cid])) for n in scopes},"parties":_json(parties[cid]),"author_people":_json([{"person_id":pid,"person_name":people[pid]["person_name"]} for pid in sorted(links.get(bid,set()))]),"end_date_status":"Bitiş tarihi mevcut" if c["end_date"] else "Bitiş tarihi bilinmiyor; süresiz varsayılmadı"})
    out["notes"].append("Sözleşme tarafı ve kitap yazarı ayrı rollerdir. Yenileme/revize/fesih kayıtları gösterilir; hukuki geçerlilik veya satış yasağı çıkarılmaz.")
    relevant_ids={_key(r.get("contract_id")) for r in rows} | {_key(r.get("other_contract_id")) for r in rows}
    if any(c["revised_end_date"] or c["renewal_end_date"] or c["termination_date"] for cid,c in contracts.items() if cid in relevant_ids):
        _gap(out,"Revize, yenileme veya fesih tarihinin ana sözleşme süresine önceliği kanıtlanmadı; bu rapor kayıtlı ana tarihleri gösterir, kesin yürürlük kararı vermez.")


def _work_reports(s,p,out):
    plans=s.rows("new_isplaniBase",{"work_id":"new_isplaniId","work_name":"new_planadi","project_id":"new_projeid","owner_id":"OwnerId","stage_id":"new_projeasamasiid","due_date":"new_tahminibitistarihi","actual_end":"new_gercekbitistarihi","work_state":"new_isEmriDurumu","cancelled":"new_isplaniiptal","created_at":"CreatedOn","updated_at":"ModifiedOn"},"r.statecode=0 AND COALESCE(r.new_isplaniiptal,0)=0 AND (r.new_isEmriDurumu IS NULL OR r.new_isEmriDurumu<>3) AND r.new_gercekbitistarihi IS NULL")
    books=s.books(); projectbooks=defaultdict(set)
    for bid,b in books.items():
        for field in ("book_project_id","project_card_id"):
            if b[field]: projectbooks[_key(b[field])].add(bid)
    for r in s.rows("new_new_proje_new_kitapBase",{"project_id":"new_projeid","book_id":"new_kitapid"},"1=1"):
        if _key(r["book_id"]) in books: projectbooks[_key(r["project_id"])].add(_key(r["book_id"]))
    projects=s.keyed(s.rows("new_projeBase",{"project_id":"new_projeId","project_name":"new_name"}),"project_id")
    stages=s.keyed(s.rows("new_projeasamalariBase",{"stage_id":"new_projeasamalariId","stage_name":"new_name"}),"stage_id")
    for r in plans:
        project=_key(r["project_id"])
        if project not in projects or not projectbooks[project]: continue
        late=bool(r["due_date"] and str(_day(r["due_date"]))<p["as_of"])
        in_window=_within(r["due_date"],p)
        missing_assignment=not bool(r["owner_id"]) or _key(r["stage_id"]) not in stages
        if p["report"]=="work_due" and not (late or in_window): continue
        if p["report"]=="work_due_missing" and not (late or (in_window and missing_assignment)): continue
        out["records"].append({"record_type":"work_detail",**r,"project_name":projects[project]["project_name"],"stage_name":stages.get(_key(r["stage_id"]),{}).get("stage_name"),"books":_json([{"book_id":bid,"book_name":books[bid]["book_name"]} for bid in sorted(projectbooks[project])]),"overdue":late,"missing_owner":not bool(r["owner_id"]),"missing_stage":_key(r["stage_id"]) not in stages})
    if p["report"]=="work_stage_history": _gap(out,"Aşamaya giriş ve çıkış tarihçesi kanıtlanmadı. ModifiedOn aşama başlangıcı sayılmadı; üç aydan uzun aynı aşamada bekleme süresi doğrulanamadı.")


def _activity_reports(s,p,out):
    people={pid:r for pid,r in s.people().items() if r["is_author"]}
    activities=s.rows("ActivityPointerBase",{"activity_id":"ActivityId","type_code":"ActivityTypeCode","state_code":"StateCode","subject":"Subject","scheduled_start":"ScheduledStart","due_date":"ScheduledEnd","owner_id":"OwnerId","created_at":"CreatedOn","regarding_id":"RegardingObjectId","regarding_type":"RegardingObjectTypeCode"},"r.ActivityTypeCode IN (4201,4212) AND r.StateCode<>2")
    appointments={_key(r["activity_id"]):r for r in activities if r["type_code"]==4201}
    tasks={_key(r["activity_id"]):r for r in activities if r["type_code"]==4212 and r["state_code"]==0}
    parties=defaultdict(set)
    for r in s.rows("ActivityPartyBase",{"activity_id":"ActivityId","person_id":"PartyId","type_code":"PartyObjectTypeCode","deleted":"IsPartyDeleted"},"r.PartyObjectTypeCode=2 AND COALESCE(r.IsPartyDeleted,0)=0"):
        if _key(r["person_id"]) in people and _key(r["activity_id"]) in appointments: parties[_key(r["activity_id"])].add(_key(r["person_id"]))
    for aid,r in appointments.items():
        if r["regarding_type"]==2 and _key(r["regarding_id"]) in people: parties[aid].add(_key(r["regarding_id"]))
    origins={_key(r["task_id"]):_key(r["appointment_id"]) for r in s.rows("TaskBase",{"task_id":"ActivityId","appointment_id":"new_randevuid","cancelled":"new_iptalmi"},"COALESCE(r.new_iptalmi,0)=0") if r["appointment_id"]}
    byperson=defaultdict(list)
    for tid,t in tasks.items():
        origin=origins.get(tid)
        if origin not in appointments: continue
        for pid in parties[origin]: byperson[pid].append((tid,origin,t))
    seen=set()
    if p["report"]=="open_author_actions":
        for pid,actions in byperson.items():
            for tid,origin,t in actions:
                meeting=appointments[origin]
                if not _within(meeting["scheduled_start"],p): continue
                out["records"].append({"record_type":"open_action","person_id":pid,"person_name":people[pid]["person_name"],"meeting_id":origin,"meeting_start":meeting["scheduled_start"],"task_id":tid,"task_subject":t["subject"],"owner_id":t["owner_id"],"due_date":t["due_date"],"same_task_reference_count":1})
    else:
        for aid,a in sorted(appointments.items(),key=lambda kv:str(kv[1]["scheduled_start"] or "")):
            if a["state_code"] not in (0,3) or not _within(a["scheduled_start"],p): continue
            for pid in sorted(parties[aid]):
                for tid,origin,t in byperson[pid]:
                    old=appointments[origin]
                    if not old["scheduled_start"] or not a["scheduled_start"] or old["scheduled_start"]>=a["scheduled_start"]: continue
                    key=(aid,pid,tid)
                    if key in seen: continue
                    seen.add(key)
                    out["records"].append({"record_type":"appointment_preparation","person_id":pid,"person_name":people[pid]["person_name"],"appointment_id":aid,"appointment_start":a["scheduled_start"],"appointment_subject":a["subject"],"prior_meeting_id":origin,"prior_meeting_start":old["scheduled_start"],"task_id":tid,"task_subject":t["subject"],"owner_id":t["owner_id"],"due_date":t["due_date"]})
    out["notes"].append("Açık işler yalnız toplantı kimliğiyle bağlı gerçek görevlerden gelir. Serbest görüşme metninden yeni görev veya aynı iş eşleşmesi üretilmedi.")


def execute_crm_report(executor, raw):
    p=validate_crm_report(raw)
    out={"records":[],"notes":[],"gaps":[]}
    s=Sources(executor); r=p["report"]
    if r in {"duplicate_customer_tax","customers_without_contacts","contact_multiple_customers","customer_geography"}: _customer_reports(s,p,out)
    elif r.startswith("contract_"): _contract_reports(s,p,out)
    elif r in {"work_due","work_due_missing","work_stage_history"}: _work_reports(s,p,out)
    elif r in {"open_author_actions","appointments_with_actions"}: _activity_reports(s,p,out)
    else: _book_reports(s,p,out)
    total=len(out["records"])
    if p["limit"] is not None:
        out["records"]=out["records"][:p["limit"]]
        out["notes"].append(f"Kullanıcının istediği sınır: {p['limit']}; raporun sınır öncesi satır sayısı {total}.")
    if not out["records"]: out["records"]=[{"record_type":"summary","record_count":0,"report":r}]
    out["gaps"]=[dict(x) for x in {json.dumps(g,sort_keys=True):g for g in out["gaps"]}.values()]
    out["output_fields"]=list(dict.fromkeys(k for row in out["records"] for k in row))
    out["numeric_fields"]=[k for k in out["output_fields"] if any(type(row.get(k)) in (int,float) for row in out["records"]) and all(row.get(k) is None or type(row.get(k)) in (int,float) for row in out["records"])]
    out["records"]=[{k:_wire(row.get(k)) for k in out["output_fields"]} for row in out["records"]]
    out["notes"].append("Kaynak: CRM güncel aktif kayıtlar; kayıt kimlikleri korunur. İlişki çoğalması kitap/kişi sayısını artırmaz.")
    executor.output_fields=out["output_fields"]; executor.numeric_fields=set(out["numeric_fields"])
    return out
