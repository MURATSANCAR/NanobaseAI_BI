"""H2 okur çekirdeğinin M37'ye (okur topluluğu) verdiği sözleşme: ince bağdaştırıcı.

M37 `okur_sources.ReadersCore` köprüde `app.state.readers_core`'u arar ve şu yöntemleri ister: `okur_envanteri`,
`izin_sagligi`, `segment_olcusu`, `ilgi_alanlari` (zorunlu) ile `kural_ilgi_alanlari`, `kural_cumlesi`, `kural_alanlari`.
H2'de bunların hiçbiri o adla yoktu, M37 «Okur çekirdeği bağlı değil» diyordu (test sunucusu kabulü 2026-09-28).

Bu dosya **mantık kopyalamaz**: sayıların hepsi H2'nin kendi işlevlerinden gelir — `readers.profiles` (etkin okur + kanal
başına son izin, `final_consent`), `readers.exportable` (dışa aktarım kuralı), `readers.sources_state` (tazelik),
`readers_segments.validate / evaluate / counts / explain / field_catalog` (segment motoru). Kural biçimi H2'ninkidir:
`{"match": "all"|"any", "rules": [{"field", "op", "value"}]}`. Kişi verisi dönmez; yalnız sayı ve etiket.

İzin sağlığı = düzeltilmesi gereken **çelişkiler** (hedef 0): aynı okurda aynı kanal için hem izin hem ret kanıtı (ret
kazanır ama kaynaklardan biri yanlıştır), ve ortak iletişim bilgisi (aynı e-posta/telefon, doğum yılları 12+ yıl ayrışan
kayıtlar). Düzeltme CRM'de/İYS'de yapılır; portal yazmaz.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import readers as R
from semantic_bridge import readers_segments as S

CONFLICT_LABELS = {
    "email": "E-posta: aynı okurda hem izin hem ret kaydı",
    "sms": "SMS: aynı okurda hem izin hem ret kaydı",
    "call": "Arama: aynı okurda hem izin hem ret kaydı",
    "kvkk": "KVKK açık rıza: aynı okurda hem onay hem ret kaydı",
}


class Provider:
    """`app.state.readers_core` olarak kaydedilir (`readers_api.register`). Motor ve kiracı her çağrıda okunur."""

    def __init__(self, engine: Callable[[], sa.engine.Engine], tenant: Callable[[], str],
                 cfg: Callable[[], dict[str, Any]] = R.settings) -> None:
        self._engine, self._tenant, self._cfg = engine, tenant, cfg

    def _profiles(self, tenant: str) -> tuple[sa.engine.Engine, dict[str, Any], list[dict[str, Any]]]:
        engine, cfg = self._engine(), self._cfg()
        return engine, cfg, R.profiles(engine, tenant, cfg)

    # ------------------------------------------------------------------ zorunlu dört yöntem

    def okur_envanteri(self, tenant: str) -> dict[str, Any]:
        """Kaynak başına okur sayısı ve izin/ilgi/çocuk doluluğu. Bir okur birden çok kaynaktaysa her satırda sayılır;
        `toplam`/`tekil` tekil okurdur."""
        engine, _cfg, profs = self._profiles(tenant)
        with engine.connect() as c:
            iys_ok = {r[0] for r in c.execute(sa.select(R.CONSENTS.c.reader_id).where(
                R.CONSENTS.c.tenant_id == tenant, R.CONSENTS.c.source == "iys", R.CONSENTS.c.status == "izinli").distinct())}
        rows: dict[str, Counter] = defaultdict(Counter)
        for p in profs:
            for s in p["sources"]:
                n = rows[s]
                n["toplam"] += 1
                n["kvkkOnayli"] += p["consent"]["kvkk"] == "izinli"
                n["iysOnayli"] += p["id"] in iys_ok
                n["epostaIzinli"] += p["consent"]["email"] == "izinli"
                n["smsIzinli"] += p["consent"]["sms"] == "izinli"
                n["ilgiAlaniDolu"] += bool(p["interests"])
                n["cocukOlasi"] += bool(p["minor"])
        order = list(R.SOURCE_LABELS) + sorted(set(rows) - set(R.SOURCE_LABELS))
        satirlar = [{"kaynak": R.SOURCE_LABELS.get(s, s), "kayitTipi": s, **{k: int(v) for k, v in rows[s].items()},
                     "silinebilir": None} for s in order if s in rows]
        tazelik = [{"kaynak": x["label"], "sonOkuma": x["at"]} for x in R.sources_state(engine, tenant, _cfg)]
        return {"toplam": len(profs), "tekil": len(profs), "satirlar": satirlar, "tazelik": tazelik}

    def izin_sagligi(self, tenant: str) -> list[dict[str, Any]]:
        engine, _cfg, profs = self._profiles(tenant)
        alive = {p["id"] for p in profs}
        seen: dict[tuple[str, str], set[str]] = defaultdict(set)
        with engine.connect() as c:
            for r in c.execute(sa.select(R.CONSENTS.c.reader_id, R.CONSENTS.c.channel, R.CONSENTS.c.status)
                               .where(R.CONSENTS.c.tenant_id == tenant)):
                if r.reader_id in alive:
                    seen[(r.reader_id, r.channel)].add(r.status)
        conflicts = Counter(ch for (_rid, ch), st in seen.items() if {"izinli", "ret"} <= st)
        out = [{"tur": f"celiski_{ch}", "ad": CONFLICT_LABELS[ch], "sayi": int(conflicts.get(ch, 0)),
                "aciklama": "Ret kazanır; yanlış olan kaynak kaydı düzeltilmeli."} for ch in (*R.CHANNELS, "kvkk")]
        shared = sum(1 for p in profs if "ortak_iletisim" in (p["attrs"].get("uyari") or []))
        out.append({"tur": "ortak_iletisim", "ad": "Ortak iletişim bilgisi (ebeveyn–çocuk olabilir)", "sayi": shared,
                    "aciklama": "Aynı e-posta/telefonu taşıyan kayıtların doğum yılları 12+ yıl ayrışıyor."})
        return out

    def segment_olcusu(self, tenant: str, kural: dict[str, Any]) -> dict[str, Any]:
        """H2 segment motoruyla sayım: toplam, en az bir kanaldan ulaşılabilir (`izinli`), e-posta ve SMS'e aktarılabilir."""
        _engine, cfg, profs = self._profiles(tenant)
        clean, _ = S.validate(kural, profs)
        mem = S.evaluate(clean, profs)
        c = S.counts(mem, cfg)
        reach = sum(1 for p in mem if any(R.exportable(p, ch, cfg)[0] for ch in R.CHANNELS))
        return {"toplam": c["total"], "izinli": reach, "eposta": c["email"]["exportable"], "sms": c["sms"]["exportable"]}

    def ilgi_alanlari(self, tenant: str) -> list[dict[str, Any]]:
        """H2'nin ilgi alanı değerleri (segment alanı «ilgi» ile aynı değer; kimlik = ad) ve okur sayısı."""
        _engine, _cfg, profs = self._profiles(tenant)
        n = Counter(i for p in profs for i in set(p["interests"]))
        return [{"id": k, "ad": k, "okur": v} for k, v in sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))]

    # ------------------------------------------------------------------ isteğe bağlı

    @staticmethod
    def kural_ilgi_alanlari(kural: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for r in (kural or {}).get("rules") or []:
            if isinstance(r, dict) and r.get("field") == "ilgi":
                v = r.get("value")
                out += [str(x) for x in (v if isinstance(v, list) else [v]) if x not in (None, "")]
        return list(dict.fromkeys(out))

    @staticmethod
    def kural_cumlesi(kural: dict[str, Any]) -> Optional[str]:
        clean, _ = S.validate(kural, None, strict=False)
        return S.explain(clean)

    def kural_alanlari(self) -> list[dict[str, Any]]:
        _engine, _cfg, profs = self._profiles(self._tenant())
        return S.field_catalog(profs)


def register(app: Any, engine: Callable[[], sa.engine.Engine], tenant: Callable[[], str]) -> Provider:
    p = Provider(engine, tenant)
    app.state.readers_core = p
    return p
