"""H2 Okur veri tabanı: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Okur sayıları okuma turunun (`readers.sync`, `timas-readers.timer`) yazdığı tablolardan (semantic_reader_*) hesaplanır:
etkin okur profili, izin kanıtları, kaynak bağları, özetler (e-posta/telefon özeti; açık değer tutulmaz). Gösterilen SQL
uçta çalışan portal okumasıdır; turun CRM'de çalıştırdığı sorgular (kişi, aday, hesap, İYS, etkinlik, ilgi, katkı,
kampanya, seçim listeleri) kaydedilmiş çalışmış metinleriyle `origin`dir.

KİŞİSEL VERİ: sorgu bilgisi yalnız SQL metnini ve satır sayısını taşır; okur satırı, ad, e-posta, telefon hiçbir zaman
kayda girmez. Ada göre arama ve KVKK başvurusu gibi aranan değerin kendisi kişisel veri olan okumalarda aranan değer SQL'e
yerleştirilmez: o okuma kayda girmez, hesap metninde nasıl yapıldığı yazılır (kimlik yalnız özetle ya da okur numarasıyla).
"""
from __future__ import annotations

from typing import Any, Optional

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge import readers as R
from semantic_bridge import readers_imports as IMP
from semantic_bridge import readers_segments as SEG

NOT_RAKAM = ("page", "pageSize", "rules", "settings", "version", "items[].version", "definition", "items[].definition",
             "birthYear", "items[].row", "run.stats.iysChannels", "segments[].version", "history[].version",
             "counts.definition", "items[].lastSnapshot.version")

F_OZET = ("Okur sayıları etkin okur profillerinden: tekil okur = birleştirmeden sonra kalan etkin okur; kaynak kaydı = okura "
          "bağlı kaynak kaydı sayısı; birden çok kaynaklı; kopya oranı = 1 − okur ÷ kayıt; kanal başına izinli / ret / "
          "bilinmiyor = izin kanıtlarından son geçerli durum (ayardaki kaynak önceliğiyle); ulaşılabilir = dışa aktarım "
          "kuralını geçen (izinli, 18 yaş altı değilse ya da ayar izin veriyorsa, KVKK şartı); ulaşılamayan nedenleri; tekil "
          "e-posta / telefon = farklı özet sayısı; birleştirme bekleyen = karar bekleyen aday çift.")
F_KAYNAK = "Kaynak durumu = okuma turunun kaynak başına son başarılı okuma anı, satır sayısı ve varsa hatası."
F_KART = ("Okur kartı: yaş = bu yıl − doğum yılı; etkinlik katılımı = bağlı kaynak kayıtlarındaki etkinlik sayısı + dosya "
          "yüklemesi olayları; kaynak kaydı = bağlı kayıt sayısı; izin = kanal başına son geçerli kanıt; segmentler = kartın "
          "profilinin onaylı segment kurallarını sağladığı segmentler.")
F_ADAY = ("Birleştirme adayı: iki okur arasındaki ortak özellikler (e-posta / telefon özeti, ad benzerliği, il, doğum yılı) "
          "kuralla puanlanır; toplam = bu durumdaki aday çift sayısı.")
F_SEGMENT = ("Segment sayısı = kural tanımını sağlayan etkin okur profilleri; kanal başına izinli / ret / bilinmiyor ve "
             "dışa aktarılabilir (izin + yaş + KVKK kuralı), dışarıda kalma nedenleri; «N okurdan» = bütün etkin okur. Son "
             "ölçüm = onaylı segmentlerin günlük sayım görüntüsü (üye listesi saklanmaz).")
F_YUKLEME = ("Yükleme sayıları dosya satırlarından: eşleşti = özeti var olan okura bağlanan, yeni, izin eksik, geçersiz / "
             "tekrar; durum başına sayı; sayfa 50 satır.")
F_DISA = "Dışa aktarım günlüğü: listede = dışa aktarılan kişi sayısı, dışarıda = izin kuralına takılan (neden başına)."
F_ARAMA = ("Arama e-posta ya da cep telefonunun özetiyle (açık değer tutulmaz), okur numarasıyla ya da (yetkiyle) CRM'de ada "
           "göre yapılır. Aranan değer kişisel veri olabileceği için arama sorgusu burada gösterilmez; sonuç satırlarının "
           "sayıları okur profilinden.")


def origins(k: P.Kaynaklar, engine: Any, tenant: str) -> list[str]:
    runs = R.sql_runs(engine, tenant)
    ids = PK.kayitli(k, runs, "okur.kaynak", None, description="Okur tablolarını dolduran okuma turunun CRM sorgusu "
                                                               "(yalnız metin; kişi satırı kayda girmez).")
    return ids


def _profiles(k: P.Kaynaklar, engine: Any, tenant: str, org: list[str]) -> list[str]:
    return [k.portal("okur.profil", "Etkin okurlar", R.active_stmt(tenant), engine, origin=org,
                     description="Etkin okur profilleri (semantic_reader_profiles); yalnız sayı alınır."),
            k.portal("okur.izin", "İzin kanıtları", R.consents_stmt(tenant), engine, origin=org,
                     description="Kanal başına izin kanıtı: durum, kaynak, tarih (semantic_reader_consents).")]


def _new(engine: Any, tenant: str) -> P.Kaynaklar:
    return P.Kaynaklar(as_of=R.last_run(engine, tenant).get("at"))


def for_overview(engine: Any, tenant: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    org = origins(k, engine, tenant)
    prof = _profiles(k, engine, tenant, org)
    pend = k.portal("okur.aday.say", "Birleştirme bekleyen aday çiftler", R.pending_stmt(tenant), engine)
    keys = k.portal("okur.ozet", "Tekil e-posta ve telefon özetleri", R.keys_stmt(tenant), engine)
    sync = k.portal("okur.tur", "Okuma turu ve kaynak durumu", R.sync_stmt(tenant), engine, origin=org)
    ref = k.hesap("ozet", F_OZET, prof + [pend, keys])
    k.alanlar({"readers": ref, "records": ref, "multiSource": ref, "duplicateRate": ref, "bySource": ref, "consent": ref,
               "reach": ref, "notReachable": ref, "minors": ref, "sharedContact": ref, "pendingCandidates": pend,
               "distinctEmails": keys, "distinctPhones": keys, "run": k.hesap("tur", F_KAYNAK, [sync]),
               "sources": "hesap:tur"})
    return k


def for_sources(engine: Any, tenant: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    org = origins(k, engine, tenant)
    ref = k.hesap("tur", F_KAYNAK, [k.portal("okur.tur", "Okuma turu ve kaynak durumu", R.sync_stmt(tenant), engine, origin=org)])
    k.alanlar({"sources": ref, "run": ref})
    return k


def for_card(engine: Any, tenant: str, rid: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    org = origins(k, engine, tenant)
    ins = [k.portal("okur.kayit", "Okur kaydı", R.reader_stmt(tenant, rid), engine, origin=org),
           k.portal("okur.bag", "Kaynak bağları", R.links_stmt(tenant, [rid]), engine),
           k.portal("okur.kart.izin", "Okurun izin kanıtları", R.reader_consents_stmt(tenant, rid), engine),
           k.portal("okur.kart.aday", "Okurun bekleyen birleştirme adayları", R.reader_candidates_stmt(tenant, rid), engine)]
    ref = k.hesap("kart", F_KART, ins + _profiles(k, engine, tenant, org))
    k.alanlar({"age": ref, "events": ref, "sources": ref, "consents": ref, "segments": ref, "pendingCandidates": ins[3],
               "interests": ref, "attrs": ref, "timeline": ref})
    return k


def for_search(engine: Any, tenant: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    prof = _profiles(k, engine, tenant, origins(k, engine, tenant))
    ref = k.hesap("arama", F_ARAMA, prof)
    k.alanlar({"items[]": ref, "total": ref})
    return k


def for_subject(engine: Any, tenant: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    prof = _profiles(k, engine, tenant, origins(k, engine, tenant))
    ref = k.hesap("kvkk", F_ARAMA + " Yükleme satırları da aynı özetle bulunur. " + F_KART, prof)
    k.alanlar({"readers[]": ref, "uploads[]": ref})
    return k


def for_candidates(engine: Any, tenant: str, status: str, page: int, size: int = 50) -> P.Kaynaklar:
    k = _new(engine, tenant)
    q = R.candidates_stmts(tenant, status, page, size)
    ins = [k.portal("okur.aday.say", "Aday çift sayısı", q["say"], engine),
           k.portal("okur.aday", "Aday çiftler (bu sayfa)", q["sayfa"], engine)]
    ref = k.hesap("aday", F_ADAY, ins + _profiles(k, engine, tenant, origins(k, engine, tenant)))
    k.alanlar({"items[]": ref, "total": ins[0]})
    return k


def for_preview(engine: Any, tenant: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    ref = k.hesap("segment", F_SEGMENT, _profiles(k, engine, tenant, origins(k, engine, tenant)))
    k.alanlar({"total": ref, "minors": ref, "email": ref, "sms": ref, "call": ref, "kvkk": ref, "of": ref})
    return k


def for_segments(engine: Any, tenant: str, status: str, domain: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    ls = k.portal("okur.segment", "Segmentler", SEG.segments_stmt(tenant, status, domain), engine)
    sn = k.portal("okur.segment.olcum", "Segment ölçüm görüntüleri", SEG.snapshots_stmt(tenant), engine,
                  origin=_profiles(k, engine, tenant, origins(k, engine, tenant)))
    k.alanlar({"items[]": k.hesap("segment", F_SEGMENT, [ls, sn])})
    return k


def for_segment(engine: Any, tenant: str, sid: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    prof = _profiles(k, engine, tenant, origins(k, engine, tenant))
    hs = k.portal("okur.segment.gecmis", "Segmentin ölçüm geçmişi", SEG.history_stmt(tenant, sid), engine)
    ref = k.hesap("segment", F_SEGMENT, prof + [hs])
    k.alanlar({"counts": ref, "history[]": hs})
    return k


def for_imports(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ref = k.hesap("yukleme", F_YUKLEME, [k.portal("okur.yukleme", "Etkinlik dosyası yüklemeleri", IMP.imports_stmt(tenant), engine)])
    k.alanlar({"items[]": ref})
    return k


def for_import(engine: Any, tenant: str, iid: str, status: str, page: int, size: int = 50) -> P.Kaynaklar:
    k = P.Kaynaklar()
    q = IMP.import_stmts(tenant, iid, status, page, size)
    ins = [k.portal("okur.yukleme.kayit", "Yükleme kaydı", q["kayit"], engine),
           k.portal("okur.yukleme.say", "Satır sayısı (süzgeçli)", q["say"], engine),
           k.portal("okur.yukleme.satir", "Satırlar (bu sayfa)", q["sayfa"], engine,
                    description="Yüklenen dosyanın satırları; kişisel değerler yetkisizde maskelenir, sorgu bilgisine girmez."),
           k.portal("okur.yukleme.durum", "Durum başına satır", q["durum"], engine)]
    ref = k.hesap("yukleme", F_YUKLEME, ins)
    for f in ("rows", "matched", "new", "rejected", "duplicates", "missingConsent", "items[]", "byStatus"):
        k.alan(f, ref)
    k.alan("total", ins[1])
    return k


def for_exports(engine: Any, tenant: str, page: int, size: int = 50) -> P.Kaynaklar:
    k = P.Kaynaklar()
    q = SEG.exports_stmts(tenant, page, size)
    ins = [k.portal("okur.disa.say", "Dışa aktarım sayısı", q["say"], engine),
           k.portal("okur.disa", "Dışa aktarımlar (bu sayfa)", q["sayfa"], engine)]
    k.alanlar({"items[]": k.hesap("disa", F_DISA, ins), "total": ins[0]})
    return k


def for_status(engine: Any, tenant: str) -> P.Kaynaklar:
    k = _new(engine, tenant)
    org = origins(k, engine, tenant)
    ref = k.hesap("tur", "Son okuma turunun sonucu: okur, bağ, birleşen ve aday sayısı. " + F_KAYNAK,
                  [k.portal("okur.tur", "Okuma turu ve kaynak durumu", R.sync_stmt(tenant), engine, origin=org)])
    k.alanlar({"result": ref})
    return k


def for_mine(engine: Any, tenant: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ls = k.portal("okur.segment.bekleyen", "Onay bekleyen segmentler", SEG.pending_stmt(tenant), engine)
    k.alanlar({"segmentsAwaiting": k.hesap("bekleyen", "Onayınızı bekleyen segment = durumu «onayda» olan ve sizin göndermediğiniz "
                                                       "segmentler.", [ls])})
    return k
