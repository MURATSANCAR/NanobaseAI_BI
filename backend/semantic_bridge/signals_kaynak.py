"""Okur sesi ve serbest not sinyali panelleri: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Okur sesi: etiketler gece sınıflamasının yazdığı tablodan (semantic_reader_voice) sayılır. Etiketlenen kayıtlar site
yorumları (sitenin yorum servisi; SQL değil, metin saklanmaz) ve Trendyol soru/yorum/iade tablolarıdır (panel dosyasından
yüklenen portal tabloları; `origin`).

Not sinyali: notlar portal tablolarından (ziyaret, bayi aksiyonu, müşteri aksiyonu) canlı okunur; CRM ziyaret notları gece
turunda okunup etiketlenir (etiket satırı tabloda, metin saklanmaz). Not metni kişisel veri içerebilir: yalnız SQL metni
kayda girer, satır asla.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from semantic_bridge import note_signal as N
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as P
from semantic_bridge import reader_voice as V

#: Rakam olmayan sayılar: pencere uzunluğu (ayar), ayarlar, son koşunun iç raporu dışındaki sürüm alanları.
NOT_RAKAM = ("gun", "ayarlar")

F_VOICE = ("Okur sesi özeti: son N gün (ayar) içindeki etiketli kayıtların kaynak × konu sayısı; konusu eşik altında kalan "
           "kayıt «belirsiz». Toplam = görünen kaynakların toplamı (kişi yalnız sayfa yetkisi olan kaynağı görür). Etiket gece "
           "yazılır: kural sözcüğü, Trendyol iade nedeni ya da Zeki AI kapalı küme seçimi + olasılık eşiği. Site yorumları "
           "sitenin yorum servisinden okunur (SQL değil; metin saklanmaz).")
F_ALERT = ("Baskı / cilt hatası kümesi: son N gün (ayar) içinde aynı ürün anahtarında eşik ve üstü «baskı / cilt hatası» etiketi; "
           "sayı = kayıt sayısı, kaynak başına kırılım; uyarı tablosuna gece yazılır, sayısı artarsa yeniden açılır.")
F_LABEL = ("Kayıt başına konu ve olasılık gece sınıflamasından (kural, iade nedeni ya da Zeki AI seçimi); olasılık yalnız "
           "Zeki AI seçiminde dolu.")
F_RUN = "Son gece turunun raporu: okunan kayıt sayısı kaynak başına, sınıflanan / değişen kayıt, uyarı ve e-posta sonucu."
F_NOTE = ("Not sinyali: carinin notları (portal ziyaret notu, bayi ve müşteri aksiyonu; gizli ziyaret notu ve iptal hariç; CRM "
          "ziyaret notları gece etiketlenen satırlardan) son N gün (ayar) içinde etiket başına sayılır; belirsiz = olasılık "
          "eşiği altında kalan not. Son notlar = en yeni 5 notun etiketi ve olasılığı. Özet: son notlardan iki cümle; "
          "düşen = sayısı notlarda geçmediği için atılan cümle sayısı.")


def _trendyol(k: P.Kaynaklar, engine: Any, tenant: str) -> list[str]:
    try:
        import sqlalchemy as sa

        from semantic_bridge.channels import trendyol as T
    except ImportError:
        return []
    ids = []
    for sid, title, table in (("trendyol.soru", "Trendyol soruları (panel yüklemesi)", T.QUESTIONS),
                              ("trendyol.yorum", "Trendyol yorumları (panel yüklemesi)", T.REVIEWS),
                              ("trendyol.iade", "Trendyol iade talepleri (panel yüklemesi)", T.CLAIMS)):
        ids.append(k.portal(sid, title, sa.select(table).where(table.c.tenant_id == tenant), engine,
                            description="Gece sınıflamasının okuduğu kayıtlar (metin zaten maskeli)."))
    return ids


def for_voice_summary(engine: Any, tenant: str, st: dict[str, Any], out: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=(out.get("sonKosu") or {}).get("_at"))
    org = _trendyol(k, engine, tenant)
    since = V.summary_since(st)
    cnt = k.portal("okursesi.ozet", "Kaynak × konu etiket sayısı", V.summary_stmt(tenant, since), engine, origin=org)
    ref = k.hesap("okursesi", F_VOICE, [cnt])
    al = k.portal("okursesi.uyari", "Baskı / cilt hatası uyarıları", V.alerts_stmt(tenant), engine)
    cl = k.portal("okursesi.kume", "Penceredeki baskı / cilt hatası etiketleri",
                  V.clusters_stmt(tenant, (V.now().date() - timedelta(days=st["defectDays"])).isoformat()), engine, origin=org)
    run = k.portal("okursesi.tur", "Son gece turu raporu", V.meta_stmt(tenant, "run"), engine)
    k.alanlar({"kaynakKonu": ref, "toplam": ref, "uyarilar": k.hesap("kume", F_ALERT, [al, cl]),
               "sonKosu": k.hesap("tur", F_RUN, [run])})
    return k


def for_voice_labels(engine: Any, tenant: str, kaynak: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    org = _trendyol(k, engine, tenant) if kaynak.startswith("trendyol") else []
    lab = k.portal("okursesi.etiket", "Kayıt başına konu etiketi", V.labels_stmt(tenant, kaynak), engine, origin=org)
    k.alan("items", k.hesap("etiket", F_LABEL, [lab]))
    return k


def _crm_note(k: P.Kaynaklar, engine: Any, tenant: str, st: dict[str, Any]) -> Optional[str]:
    """Gece turunun CRM ziyaret notu sorgusu (başlangıç günü = son CRM etiketleme günü − ayardaki gün)."""
    if not st.get("crmColumn"):
        return None
    with engine.connect() as c:
        last = c.execute(N.crm_last_run_stmt(tenant)).scalar()
    if not last:
        return None
    try:
        sql = N.crm_notes_sql(st["schema"], st["crmColumn"], last.date() - timedelta(days=st["crmDays"]))
    except N.NoteError:
        return None
    return k.sorgu("notsinyali.crm", "CRM ziyaret notları (gece turu)", "crm", sql, database=PK.crm_db(), ran_at=last,
                   description="Gece etiketlenen CRM «Cari Ziyareti» notları; not metni saklanmaz.")


def for_note_view(engine: Any, tenant: str, code: str, st: dict[str, Any]) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ins = [k.portal(f"notsinyali.{src}", f"{N.SOURCES.get(src, src)} (portal)", stmt, engine,
                    description="Carinin notları; not metni kişisel veri içerebilir, yalnız sorgu gösterilir.")
           for src, stmt in N.portal_notes_stmts(engine, tenant, {code}).items()]
    crm = _crm_note(k, engine, tenant, st)
    ins.append(k.portal("notsinyali.etiket", "Notların gece etiketi", N.signal_rows_stmt(tenant, code), engine,
                        origin=[crm] if crm else []))
    ozet = k.portal("notsinyali.ozet", "Kayıtlı not özeti", N.summary_row_stmt(tenant, code), engine)
    ref = k.hesap("not", F_NOTE, ins + [ozet])
    k.alanlar({"sayilar": ref, "belirsiz": ref, "sonNotlar": ref, "ozet": ref})
    return k
