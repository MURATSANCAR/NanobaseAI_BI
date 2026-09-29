"""Read-only financial audit. Source notes are evidence, not executable rules.

Only deterministic accounting checks run here. Tax conclusions, source formula
conflicts, physical inventory and document authenticity require separate review.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import logging
from pathlib import Path
import threading
import os
import re
import uuid

from fastapi import HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from .financial_audit_rules import extend_ratios, evaluate, pair_sql, pair_results
from .financial_audit_evidence import read_evidence, document_sql
from .financial_audit_deep import read_deep, exception_sql, DEFINITIONS
from .financial_audit_snapshot import AuditSnapshots, atomic_json
from . import financial_audit_kaynak as K
from . import provenance as PV

log = logging.getLogger(__name__)
REVISION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class ReviewNote(BaseModel):
    version: int = Field(ge=0)
    state: str = Field(pattern='^(open|in_review|evidence_supplied)$')
    owner: str = Field(default='', max_length=100)
    note: str = Field(min_length=3, max_length=4000)
    evidence: list[str] = Field(default_factory=list, max_length=20)


def archive_root():
    return Path(os.getenv('FINANCIAL_AUDIT_DATA_DIR', '/data/nanobaseai/bi/var/financial-audit/workpapers'))


def dec(value):
    return Decimal(str(value or 0))


#: SQL kurucuları tabloları 2026 kopyasının adıyla (LG_411_…) yazar; çalıştırmadan önce denetlenen yılın Logo firma
#: kopyasına çevrilir (her yıl ayrı firma numarasındadır: ör. 2021–2025 LG_211, 2026 LG_411). Sabit firma kodu yok.
CANONICAL_FIRM = '411'


def audit_years():
    """Denetimi açılan yıllar (kaynak kopyası mutabık kılınmış olanlar). Ayar: FINANCIAL_AUDIT_YEARS (virgüllü)."""
    years = sorted({int(y) for y in re.findall(r'\d{4}', os.getenv('FINANCIAL_AUDIT_YEARS', '2026'))})
    return years or [2026]


def firm_sql(sql, firm):
    """Kurucunun yazdığı kopya adlarını (LG_411_) denetlenen yılın firma kopyasına çevirir."""
    if not re.fullmatch(r'\d{3}', str(firm or '')):
        raise ValueError('Logo firma numarası üç haneli olmalı.')
    return re.sub(rf'\bLG_{CANONICAL_FIRM}_', f'LG_{firm}_', sql)


def resolve_firm(run, year):
    """Yıl → Logo firma kopyası (`L_CAPIPERIOD`, bütçe/finans modüllerinin ortak kuralı). Yoksa hata."""
    from .budget_sources import firms_by_year
    firms = firms_by_year(run)
    if year not in firms:
        raise HTTPException(409, f"Logo'da {year} yılının firma kopyası (dönemi) bulunamadı; denetim doğrulanamadı.")
    return firms[year]


def register(app, runtime, authorize):
    lock = threading.Lock()
    review_lock = threading.Lock()
    firms = {}
    firm_lock = threading.Lock()

    def firm_for(year):
        """Denetlenen yılın firma kopyası; Logo'dan bir kez okunur (süreç ömrü boyunca)."""
        with firm_lock:
            if year not in firms:
                r = runtime()

                def run(sql):
                    # Köprünün Logo bağlantı havuzu: kendi bağlantısını alır, sunucu sınırına uyar.
                    _cols, rows, _truncated = r.connector.execute(sql, 10000)
                    return rows
                firms[year] = resolve_firm(run, year)
            return firms[year]

    def logo_db():
        from . import provenance as PV
        try:
            return PV.connection_database(runtime().settings.connection_file)
        except Exception:  # noqa: BLE001 — veritabanı adı yoksa USE satırı yazılmaz
            return None

    @app.get("/api/v1/financial-audit/catalog")
    def catalog(request: Request):
        authorize(request)
        path = Path(__file__).resolve().parents[2] / 'configs/financial-audit/source.json'
        if not path.exists():
            raise HTTPException(503, 'Kontrol kaynağı bu kurulumda bulunamadı.')
        return json.loads(path.read_text(encoding='utf-8'))

    def context(year):
        # Only declared, inspected backups are enabled (FINANCIAL_AUDIT_YEARS). Older copies require
        # opening/closing and source reconciliation before activation.
        if year not in audit_years():
            raise HTTPException(422, f"Bu kurulumda doğrulanan kaynak dönemi: {', '.join(map(str, audit_years()))}.")
        return (date(year, 1, 1), date(year + 1, 1, 1))

    def query(sql, year):
        r = runtime()
        # The year's own Logo company copy (L_CAPIPERIOD), never a fixed number. A dated predicate
        # alone does not pin master tables such as FAYEAR to the declared copy.
        firm = firm_for(year)
        sql = firm_sql(sql, firm)
        scope = {'n0': firm}
        physical = r._physical(sql, context(year), scope=scope)
        if any(code != firm for code in re.findall(r'\bLG_(\d+)_', physical, re.I)):
            raise HTTPException(409, f'Sorgu {year} yılının kaynak kopyasından (firma {firm}) başka bir yedeğe yönlendi.')
        result = r.run_sql(sql, 10000, context(year), scope=scope, use_cache=False)
        if any(code != firm for code in re.findall(r'\bLG_(\d+)_', result.get('physicalSql',''), re.I)):
            raise HTTPException(409, 'Yanıtın kaynak kopyası doğrulanamadı.')
        result['firm'] = firm
        if result.get("truncated"):
            raise HTTPException(409, "Sonuç kesildi; denetim tamamlanamadı.")
        return result

    def where(year):
        context(year)
        return f"L.DATE_ >= '{year}0101' AND L.DATE_ < '{year + 1}0101' AND L.CANCELLED=0 AND F.CANCELLED=0"

    joins = """FROM dbo.LG_411_01_EMFLINE L
      LEFT JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF
      LEFT JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=L.ACCFICHEREF"""

    @app.get("/api/v1/financial-audit/overview")
    def overview(request: Request, year: int | None = None):
        authorize(request)
        context(year or snapshots.year)
        report = snapshots.load()
        if report is None:
            raise HTTPException(503, 'İlk denetim raporu arka planda hazırlanıyor. Hazır olduğunda otomatik gösterilecek.')
        out = dict(report, cached=True, refresh=snapshots.status())
        return PV.bagla(out, lambda: K.for_report(out, logo_db()))

    @app.get('/api/v1/financial-audit/refresh-status')
    def refresh_status(request: Request):
        authorize(request)
        return snapshots.status()

    @app.post('/api/v1/financial-audit/refresh', status_code=202)
    def refresh(request: Request):
        authorize(request)
        return snapshots.refresh()

    def build_report(year):
        # Only the background snapshot publisher invokes this expensive calculation.
        with lock:
            started_at = datetime.now(timezone.utc).isoformat()
            # Sorgu bilgisi: rapordaki her rakamın çalışan SQL'i (fiziksel metin), satır, süre ve an; kimliğiyle.
            queries = {}

            def rec(qid, title, res):
                queries[qid] = {'title': title, 'sql': res.get('physicalSql'), 'rows': len(res.get('records') or []),
                                'dbMs': res.get('dbMs'), 'at': datetime.now(timezone.utc).isoformat()}
                return res
            try:
                firm = firm_for(year)
                sql = f"""SELECT A.LOGICALREF AS accountRef,A.CODE AS code,A.DEFINITION_ AS name,
                  A.ACCTYPE AS accountType, COUNT(*) AS lineCount,
                  SUM(CAST(L.DEBIT AS decimal(28,4))) AS debit,
                  SUM(CAST(L.CREDIT AS decimal(28,4))) AS credit,
                  SUM(CASE WHEN L.DEBIT IS NULL OR L.CREDIT IS NULL THEN 1 ELSE 0 END) AS nullAmounts,
                  SUM(CASE WHEN F.TRCODE=1 THEN 1 ELSE 0 END) AS openingLines,
                  MIN(L.DATE_) AS firstDate,MAX(L.DATE_) AS lastDate
                  {joins} WHERE {where(year)}
                  GROUP BY A.LOGICALREF,A.CODE,A.DEFINITION_,A.ACCTYPE ORDER BY A.CODE"""
                result = rec('hesaplar', 'Hesap bakiyeleri ve hareket sayıları', query(sql, year))
                accounts = []
                for a in result["records"]:
                    a = dict(a)
                    balance = dec(a["debit"]) - dec(a["credit"])
                    a["balance"] = str(balance)
                    # Live profiling found 374/379 cards marked debit, including liabilities.
                    # Do not infer normal balances from this unreliable card setting.
                    # Source pp.61/65 explicitly define cash/received cheques as debit or zero.
                    a["unexpectedSign"] = str(a['code'] or '')[:3] in {'100', '101'} and balance < Decimal('-.01')
                    accounts.append(a)
                total_lines = sum(a["lineCount"] for a in accounts)
                debit = sum((dec(a["debit"]) for a in accounts), Decimal(0))
                credit = sum((dec(a["credit"]) for a in accounts), Decimal(0))
                wrong = [a for a in accounts if a["unexpectedSign"]]
                missing = [a for a in accounts if not a["code"]]
                nulls = sum(a["nullAmounts"] for a in accounts)
                # Exact, full grouped answer. Not the count of a paginated preview.
                slip_sql = f"""SELECT COUNT(*) AS affected,
                  SUM(ABS(X.difference)) AS amount FROM (
                  SELECT L.ACCFICHEREF, SUM(CAST(L.DEBIT AS decimal(28,4)) - CAST(L.CREDIT AS decimal(28,4))) AS difference
                  {joins} WHERE {where(year)} GROUP BY L.ACCFICHEREF
                  HAVING ABS(SUM(CAST(L.DEBIT AS decimal(28,4)) - CAST(L.CREDIT AS decimal(28,4)))) > 0.01) X"""
                slips = rec('fisDenge', 'Fiş bazında borç–alacak eşitliği', query(slip_sql, year))
                imbalance = slips["records"][0]
                integrity = rec('butunluk', 'Hareket–fiş bağlantısı ve iptal', query(f"""SELECT COUNT(*) AS sourceRows,
                  SUM(CASE WHEN F.LOGICALREF IS NULL THEN 1 ELSE 0 END) AS missingSlip,
                  SUM(CASE WHEN F.CANCELLED<>0 THEN 1 ELSE 0 END) AS cancelledSlip
                  FROM dbo.LG_411_01_EMFLINE L LEFT JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=L.ACCFICHEREF
                  WHERE L.DATE_ >= '{year}0101' AND L.DATE_ < '{year+1}0101' AND L.CANCELLED=0""", year))
                source_integrity = integrity['records'][0]
                checks = [
                    {"id": "trial-balance", "title": "Mizan borç–alacak eşitliği", "affected": int(abs(debit-credit) > Decimal('.01')),
                     "amount": str(abs(debit-credit)), "formula": "Σ borç − Σ alacak; tolerans 0,01 TL", "origin": "Ek kontrol"},
                    {"id": "slip-balance", "title": "Fiş bazında borç–alacak eşitliği", "affected": imbalance["affected"],
                     "amount": str(imbalance["amount"] or 0), "formula": "Her fişte |Σ borç − Σ alacak| > 0,01 TL", "origin": "Ek kontrol"},
                    {"id": "account-sign", "title": "Kasa ve alınan çeklerde ters bakiye", "affected": len(wrong),
                     "amount": str(sum((abs(dec(a["balance"])) for a in wrong), Decimal(0))),
                     "formula": "100 Kasa ve 101 Alınan Çekler alt hesaplarında net alacak bakiyesi > 0,01 TL. Diğer hesap karakterleri henüz doğrulanmadı.", "origin": "Kaynak s. 61, 65"},
                    {"id": "account-link", "title": "Muhasebe hesap kartı bağlantısı", "affected": sum(a["lineCount"] for a in missing),
                     "amount": None, "formula": "Hareketin ACCOUNTREF alanı hesap kartına bağlanıyor mu?", "origin": "Ek veri kontrolü"},
                    {"id": "null-amount", "title": "Eksik borç veya alacak tutarı", "affected": nulls,
                     "amount": None, "formula": "Borç veya alacak alanı NULL olan hareket sayısı", "origin": "Ek veri kontrolü"},
                    {"id": "slip-link", "title": "Muhasebe fişi bağlantısı", "affected": source_integrity['missingSlip'] or 0,
                     "amount": None, "formula": "İptal edilmemiş hareketin bağlı olduğu fiş mevcut mu?", "origin": "Ek veri kontrolü"},
                ]
                for check in checks:
                    query_result = slips if check['id']=='slip-balance' else integrity if check['id']=='slip-link' else result
                    check['sql'] = query_result.get('physicalSql')
                    check['sqlPurpose'] = ('Bu sorgu bulgunun hesaplandığı gerçek veri okumasıdır. Hesap bazındaki sonuçlar yukarıdaki kontrol ölçütüne göre değerlendirilir.'
                        if check['id'] not in {'slip-balance','slip-link'} else 'Bu sorgu rapor hazırlanırken çalıştırılmıştır; gösterilen bulgu sayısı bu sonuçtan hesaplanmıştır.')
                incomplete = nulls or source_integrity['missingSlip'] or source_integrity['cancelledSlip'] or missing
                for check in checks:
                    check["status"] = "finding" if check['affected'] else "unverified" if not total_lines or incomplete else "passed"
                def b(prefix):
                    return sum((dec(a["balance"]) for a in accounts if str(a["code"] or '').startswith(prefix)), Decimal(0))
                current, stocks, short, long, equity = b('1'), b('15'), -b('3'), -b('4'), -b('5')
                asset = b('1') + b('2')
                closing_gap = asset - short - long - equity
                # Unclosed income/cost accounts must not be treated as finalized equity.
                closing_required = {11, 12, 13, 14, 15, 20}
                specs = [
                    (2, 'Cari oran', current, short, 'Dönen varlıklar / kısa vadeli yabancı kaynaklar'),
                    (3, 'Asit-test oranı', current-stocks, short, '(Dönen varlıklar − stoklar) / kısa vadeli yabancı kaynaklar'),
                    (4, 'Nakit oranı', b('10')+b('11'), short, '(Hazır değerler + menkul kıymetler) / kısa vadeli yabancı kaynaklar'),
                    (5, 'Stokların dönen varlıklardaki payı', stocks, current, 'Stoklar / dönen varlıklar'),
                    (6, 'Stokların varlıklardaki payı', stocks, asset, 'Stoklar / toplam varlıklar'),
                    (7, 'Stok bağımlılık oranı', short-b('10')-b('11'), stocks, '(Kısa vadeli borçlar − hazır değerler − menkul kıymetler) / stoklar'),
                    (8, 'Kısa vadeli alacakların dönen varlıklardaki payı', b('12')+b('13'), current, '(Ticari + diğer kısa vadeli alacaklar) / dönen varlıklar'),
                    (9, 'Kısa vadeli alacakların varlıklardaki payı', b('12')+b('13'), asset, '(Ticari + diğer kısa vadeli alacaklar) / toplam varlıklar'),
                    (10, 'Finansal kaldıraç', short+long, asset, 'Yabancı kaynaklar / toplam varlıklar'),
                    (11, 'Özkaynak oranı', equity, asset, 'Özkaynaklar / toplam varlıklar'),
                    (12, 'Özkaynak / borç oranı', equity, short+long, 'Özkaynaklar / yabancı kaynaklar'),
                    (13, 'Kısa vadeli kaynakların payı', short, short+long+equity, 'Kısa vadeli yabancı kaynaklar / toplam kaynaklar'),
                    (14, 'Uzun vadeli kaynakların payı', long, short+long+equity, 'Uzun vadeli yabancı kaynaklar / toplam kaynaklar'),
                    (15, 'Uzun vadeli borç / devamlı sermaye', long, long+equity, 'Uzun vadeli yabancı kaynaklar / (uzun vadeli yabancı kaynaklar + özkaynaklar)'),
                    (18, 'Borçların vade yapısı', short, short+long, 'Kısa vadeli yabancı kaynaklar / yabancı kaynaklar'),
                    (19, 'Banka kredileri / varlıklar', -b('300')-b('303')-b('400'), asset, '(300 + 303 + 400 net alacak bakiyesi) / varlıklar'),
                    (20, 'Banka kredileri / özkaynaklar', -b('300')-b('303')-b('400'), equity, '(300 + 303 + 400 net alacak bakiyesi) / özkaynaklar'),
                    (21, 'Dönen varlıkların payı', current, asset, 'Dönen varlıklar / toplam varlıklar'),
                ]
                def calculable(n, den):
                    return den > 0 and total_lines and not incomplete and not (n in closing_required and abs(closing_gap) > Decimal('.01'))
                ratios = [{"note": n, "title": title, "numerator": str(num), "denominator": str(den),
                           "value": str(num/den) if calculable(n, den) else None,
                           "formula": formula, "status": "calculated" if calculable(n, den) else "unverified",
                           "reason": "Özkaynak / bilanço kapanış uyumu doğrulanmadı." if n in closing_required and abs(closing_gap) > Decimal('.01') else "Payda sıfır/negatif veya veri eksik." if not calculable(n, den) else None}
                          for n, title, num, den, formula in specs]
                out = {"year": year, "revision": REVISION, "computedAt": datetime.now(timezone.utc).isoformat(),
                       "source": f"Logo · {year} işlem dönemi · firma {firm}", "firm": firm, "currency": "TRY",
                       "firstDate": min((a['firstDate'] for a in accounts), default=None),
                       "lastDate": max((a['lastDate'] for a in accounts), default=None),
                       "lineCount": total_lines, "debit": str(debit), "credit": str(credit),
                       "accounts": accounts, "checks": checks, "ratios": ratios, "truncated": False,
                       "closingGap": str(closing_gap),
                       "cached": False, "dbMs": result.get('dbMs', 0) + slips.get('dbMs', 0) + integrity.get('dbMs', 0),
                       "sourceIntegrity": source_integrity,
                       "sql": [result.get('physicalSql'), slips.get('physicalSql'), integrity.get('physicalSql')],
                       "limitations": ["Bu sonuç bağımsız denetim görüşü değildir; bulgular inceleme adaylarıdır.",
                                        "Logo hesap karakterleri tutarsız olduğundan ters bakiye kontrolü yalnız 100/101 hesaplarında yapılır.",
                                        "Aktif ile 3/4/5 hesap sınıfları arasında fark varsa özkaynağa bağlı oranlar hesaplanmaz; ara dönem kapanışı teyit edilmelidir.",
                                        "Oranlar açılış dahil net hesap bakiyelerinden hesaplanır; sektör eşiğiyle başarı hükmü verilmez.",
                                        "Fiş kontrolü ve mizan ayrı sorgulardır. Kaynak yedek değişirse yeniden çalıştırılmalıdır.",
                                        "Eksik/iptal fiş başlıklarına ait hareketler bu mali kapsama dahil değildir.",
                                        "Belge, beyanname, mutabakat ve mevzuat gerektiren kontroller otomatik geçmez."]}
                profile = rec('profil', 'Hesap profili: açılış, dönem, döviz, eksik belge alanları', query(f"""SELECT A.CODE AS code,A.LOGICALREF AS accountRef,
                    SUM(CASE WHEN F.TRCODE=1 THEN CAST(L.DEBIT AS decimal(28,4)) ELSE 0 END) AS openingDebit,
                    SUM(CASE WHEN F.TRCODE=1 THEN CAST(L.CREDIT AS decimal(28,4)) ELSE 0 END) AS openingCredit,
                    SUM(CASE WHEN F.TRCODE<>1 THEN CAST(L.DEBIT AS decimal(28,4)) ELSE 0 END) AS periodDebit,
                    SUM(CASE WHEN F.TRCODE<>1 THEN CAST(L.CREDIT AS decimal(28,4)) ELSE 0 END) AS periodCredit,
                    SUM(CASE WHEN L.TRCURR IS NOT NULL AND L.TRCURR NOT IN (0,160) THEN 1 ELSE 0 END) AS foreignRows,
                    SUM(CASE WHEN NULLIF(LTRIM(RTRIM(L.INVOICENO)),'') IS NULL THEN 1 ELSE 0 END) AS missingInvoiceNumber,
                    SUM(CASE WHEN L.DOCDATE IS NULL OR L.DOCDATE<'19010101' THEN 1 ELSE 0 END) AS missingDocumentDate
                    {joins} WHERE {where(year)} GROUP BY A.CODE,A.LOGICALREF ORDER BY A.CODE""", year))
                out['profiles'] = profile['records']
                pair_read = rec('karsiHesap', 'Fiş karşı hesap kontrolleri', query(pair_sql(joins, where(year)), year))
                out['pairChecks'] = pair_results(pair_read['records'][0])
                vat = rec('kdv', 'KDV hesapları (190, 191, 391) ay ay hareket', query(f"""SELECT MONTH(L.DATE_) AS month,LEFT(A.CODE,3) AS code,
                    SUM(CAST(L.DEBIT AS decimal(28,4))-CAST(L.CREDIT AS decimal(28,4))) AS movement
                    {joins} WHERE {where(year)} AND LEFT(A.CODE,3) IN ('190','191','391')
                    GROUP BY MONTH(L.DATE_),LEFT(A.CODE,3) ORDER BY month,code""", year))
                balances = {k:Decimal(0) for k in ['190','191','391']}
                out['vatMonths'] = []
                last_month = int(str(out['lastDate'])[5:7]) if out['lastDate'] else 0
                for month in range(1,last_month+1):
                    for row in vat['records']:
                        if row['month']==month:
                            balances[row['code']] += dec(row['movement'])
                    out['vatMonths'].append({'month':month,'balance':str(balances['191']+balances['391']),
                        'accounts':{k:str(v) for k,v in balances.items()},'status':'needs_evidence',
                        'partialMonth':month==last_month})
                extend_ratios(out, profile['records'])
                out['supportingEvidence'] = read_evidence(query, year)
                out['deepAudit'] = read_deep(query, year, out['lastDate'])
                out['coverage'] = evaluate(out, profile['records'])
                # Preserve the exact executed SQL beside each supported observation.
                # A source read is not falsely presented as an executable legal rule.
                for control in out['coverage']['items']:
                    for component in control['components']:
                        kind = component.get('id')
                        observation_query = (result if kind in {'account-scope','balance-sign'} else
                            pair_read if kind=='voucher-counterpart' else
                            profile if kind=='fx-profile' else
                            vat if kind and kind.startswith('vat-') else None)
                        if observation_query:
                            component['sql'] = observation_query.get('physicalSql')
                            component['sqlPurpose'] = 'Bu sorgu rapor hazırlanırken çalıştırılmıştır. Sonuçları, yukarıda açıklanan hesap ve kontrol ölçütlerine göre değerlendirilmiştir; sorgu birden fazla hesabı içerebilir.'

                out['sql'].append(profile.get('physicalSql'))
                out['sql'].extend([pair_read.get('physicalSql'),vat.get('physicalSql')])
                out['dbMs'] += profile.get('dbMs', 0)+pair_read.get('dbMs',0)+vat.get('dbMs',0)
                out['sql'].extend(out['supportingEvidence']['sql'])
                out['dbMs'] += out['supportingEvidence']['dbMs']
                out['sql'].extend(out['deepAudit']['sql'])
                out['dbMs'] += out['deepAudit']['dbMs']
                for prefix, block in (('belge', out['supportingEvidence']), ('derin', out['deepAudit'])):
                    for key, q in (block.get('executed') or {}).items():
                        queries[f'{prefix}.{key}'] = q
                out['queries'] = queries
                out['runId'] = uuid.uuid4().hex
                out['sourceReadStartedAt'] = started_at
                out['computedAt'] = datetime.now(timezone.utc).isoformat()
                out['readConsistency'] = 'Aynı yedek üzerinde ardışık sorgular; veritabanı snapshot transaction değildir.'
                out = json.loads(json.dumps(out, ensure_ascii=False, default=str))
                # Private immutable workpaper. UI and exports can pin this exact run.
                root = archive_root()
                root.mkdir(parents=True, exist_ok=True, mode=0o700)
                path = root / (out['runId'] + '.json')
                atomic_json(path, out)
                meta = {k:out[k] for k in ['runId','computedAt','year','source','lastDate','lineCount','revision']}
                meta_temp = root/(out['runId']+'.meta.tmp')
                with meta_temp.open('x') as f:
                    os.chmod(f.name,0o600)
                    json.dump(meta,f,ensure_ascii=False)
                meta_temp.replace(root/(out['runId']+'.meta.json'))
                return out
            except HTTPException:
                raise
            except Exception:
                log.exception("Financial audit could not read the source")
                raise HTTPException(503, "Logo verisi okunamadı. Denetim DOĞRULANAMADI; tekrar deneyin.")

    def load_run(run_id):
        if not re.fullmatch('[0-9a-f]{32}', run_id):
            raise HTTPException(422, 'Geçersiz rapor kimliği.')
        path = archive_root() / (run_id+'.json')
        if not path.exists():
            raise HTTPException(404, 'Rapor bulunamadı.')
        return json.loads(path.read_text())

    #: Rapor özeti dosyası → (mtime_ns, boyut, içerik). Hız 4. tur (2026-09-29): arşivde 1.000'i aşkın rapor var; her
    #: açılışta hepsi yeniden açılıp çözülüyordu. Dosya değişmedikçe (değişim anı + boyut) çözülmüş içerik kullanılır;
    #: liste ve sıra her istekte klasörden okunur (silinen rapor düşer, yeni rapor eklenir).
    meta_cache: dict[str, tuple[int, int, dict]] = {}

    @app.get('/api/v1/financial-audit/runs')
    def list_runs(request: Request):
        authorize(request)
        root = archive_root()
        # Bütün arşiv döner (sessiz tavan yok); seçici yazarak arar ve listeyi pencereleyerek çizer.
        found = []
        if root.exists():
            with os.scandir(root) as it:
                for e in it:
                    if e.name.endswith('.meta.json') and e.is_file():
                        st = e.stat()
                        found.append((st.st_mtime, e.name, st.st_mtime_ns, st.st_size, e.path))
        found.sort(key=lambda x: x[0], reverse=True)
        items = []
        for _mt, name, mt_ns, size, path in found:
            hit = meta_cache.get(name)
            if hit is None or hit[0] != mt_ns or hit[1] != size:
                hit = (mt_ns, size, json.loads(Path(path).read_text()))
                meta_cache[name] = hit
            items.append(dict(hit[2]))
        for gone in set(meta_cache) - {f[1] for f in found}:
            meta_cache.pop(gone, None)
        return {'items':items, 'total':len(items)}

    @app.get('/api/v1/financial-audit/runs/{run_id}')
    def saved_run(request: Request, run_id: str):
        authorize(request)
        out = load_run(run_id)
        return PV.bagla(out, lambda: K.for_report(out, logo_db()))

    @app.get('/api/v1/financial-audit/runs/{run_id}/export')
    def export_run(request: Request, run_id: str):
        authorize(request)
        run = load_run(run_id)
        # Download the pinned, immutable computation. Do not recompute on export
        # or substitute the current catalog for the version used by this run.
        payload = (archive_root() / (run_id+'.json')).read_bytes()
        return Response(content=payload, media_type='application/json', headers={
            'Content-Disposition':f'attachment; filename="finansal-denetim-{run["year"]}-{run_id}.json"',
            'X-Content-SHA256':hashlib.sha256(payload).hexdigest(),
            'Cache-Control':'private, no-store',
            'X-Content-Type-Options':'nosniff',
        })

    @app.get('/api/v1/financial-audit/runs/{run_id}/exceptions/{check_id}')
    def exception_rows(request: Request, run_id: str, check_id: str, page: int = Query(0,ge=0,le=10000)):
        authorize(request)
        run=load_run(run_id)
        if check_id not in DEFINITIONS or not any(c['id']==check_id for c in run.get('deepAudit',{}).get('checks',[])):
            raise HTTPException(404,'Bu raporda istenen karşılaştırma bulunamadı.')
        result=query(exception_sql(check_id,run['year'],run['lastDate'],page),run['year'])
        records=result['records']
        total=int(records[0]['totalRows']) if records else 0
        if page and not records:
            from .financial_audit_deep import source_sql
            definition=DEFINITIONS[check_id]
            count=query(f"SELECT COUNT(*) AS totalRows FROM ({source_sql(definition[1],run['year'],run['lastDate'])}) S WHERE {definition[2]}",run['year'])
            total=int(count['records'][0]['totalRows'])
        out = {'items':records,'total':total,'page':page,'checkId':check_id,'runId':run_id,
               'asOf':str(run['lastDate'])[:10],'separateRead':True,'readAt':datetime.now(timezone.utc).isoformat(),
               'truncated':False,'sql':result.get('physicalSql'),'dbMs':result.get('dbMs'),'firm':result.get('firm')}
        return PV.bagla(out, lambda: K.for_live(out, 'denetim.bulgu', f"Bulgu kayıtları · {DEFINITIONS[check_id][0]}",
                                                 int(run['year']), logo_db(), DEFINITIONS[check_id][3]))

    def review_path(run_id, control_id):
        run = load_run(run_id)
        if not any(x['id']==control_id for x in run['coverage']['items']):
            raise HTTPException(404, 'Bu raporda kontrol bulunamadı.')
        return archive_root() / (run_id+'-'+control_id+'.reviews.json')

    @app.get('/api/v1/financial-audit/runs/{run_id}/reviews/{control_id}')
    def read_review(request: Request, run_id: str, control_id: str):
        authorize(request)
        path = review_path(run_id, control_id)
        with review_lock:
            history = json.loads(path.read_text()) if path.exists() else []
        return {'version':len(history), 'history':history}

    @app.post('/api/v1/financial-audit/runs/{run_id}/reviews/{control_id}')
    def write_review(request: Request, run_id: str, control_id: str, body: ReviewNote):
        authorize(request)
        if body.state=='evidence_supplied' and not body.evidence:
            raise HTTPException(422, 'Kanıt sunuldu durumu için belge referansı gerekiyor.')
        if any(len(x)>1000 or not x.strip() for x in body.evidence):
            raise HTTPException(422, 'Belge referansı boş olamaz ve 1000 karakteri aşamaz.')
        path = review_path(run_id, control_id)
        with review_lock:
            # Cross-worker optimistic concurrency and atomic replacement.
            import fcntl
            with (archive_root()/'.reviews.lock').open('a') as lf:
                fcntl.flock(lf, fcntl.LOCK_EX)
                history = json.loads(path.read_text()) if path.exists() else []
                if body.version != len(history):
                    raise HTTPException(409, 'İnceleme başka bir kullanıcı tarafından değiştirildi; yeniden yükleyin.')
                event = body.model_dump()
                from . import board
                try:
                    actor = board.user_of(request.headers.get('cookie', ''))
                except board.NoUser:
                    # Authorized loopback/caller requests have no portal cookie.
                    actor = 'authenticated-service'
                event.update({'at':datetime.now(timezone.utc).isoformat(), 'version':len(history)+1,
                              'actor':actor})
                history.append(event)
                temp = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                with temp.open('x') as f:
                    os.chmod(temp,0o600)
                    json.dump(history,f,ensure_ascii=False)
                temp.replace(path)
        return {'version':len(history),'history':history,
                'message':'İnceleme notu kaydedildi. Otomatik kontrol sonucu değiştirilmedi; kanıt kabulü ayrıca gerekir.'}

    @app.get('/api/v1/financial-audit/documents')
    def documents(request: Request, year: int | None = None, page: int = Query(0,ge=0,le=100000),
                  main_account: int | None = Query(None,ge=100,le=999)):
        authorize(request)
        year = year or snapshots.year
        context(year)
        try:
            result = query(document_sql(year,page,main_account),year)
            out = {'items':result['records'],'total':result['records'][0]['totalRows'] if result['records'] else 0,
                   'page':page,'readAt':datetime.now(timezone.utc).isoformat(),'separateRead':True,
                   'sql':result.get('physicalSql'),'dbMs':result.get('dbMs'),'firm':result.get('firm')}
            return PV.bagla(out, lambda: K.for_live(out, 'denetim.belge', 'E-defter belge kayıtları', year, logo_db(),
                                                     'Belge türü, no, tarih, ödeme şekli ve kaynak bayrakları (belge yok, '
                                                     'ödeme yok) Logo\'da saklandığı gibi; sayfa başına 50 kayıt, toplam '
                                                     'sayfalamadaki sayıdır.'))
        except HTTPException:
            raise
        except Exception:
            log.exception('Audit e-ledger details failed')
            raise HTTPException(503,'Logo e-defter belge detayları okunamadı.')

    @app.get("/api/v1/financial-audit/lines")
    def lines(request: Request, year: int | None = None, account: int = Query(..., ge=1), page: int = Query(0, ge=0, le=100000)):
        authorize(request)
        year = year or snapshots.year
        context(year)
        # Separate live read is explicit; never advertised as the overview snapshot.
        sql = f"""SELECT L.LOGICALREF AS lineRef,F.LOGICALREF AS slipRef,F.FICHENO AS slipNo,
          L.DATE_ AS date,A.CODE AS accountCode,A.DEFINITION_ AS accountName,
          L.DEBIT AS debit,L.CREDIT AS credit,L.LINEEXP AS description,F.DOCODE AS documentNo,
          COUNT(*) OVER() AS totalRows {joins}
          WHERE {where(year)} AND L.ACCOUNTREF={account}
          ORDER BY L.DATE_,L.LOGICALREF OFFSET {page*50} ROWS FETCH NEXT 50 ROWS ONLY"""
        try:
            result = query(sql, year)
            out = {"items": result['records'], "total": result['records'][0]['totalRows'] if result['records'] else 0,
                   "page": page, "readAt": datetime.now(timezone.utc).isoformat(), "dbMs": result.get('dbMs'),
                   "sql": result.get('physicalSql'), "separateRead": True, "firm": result.get('firm')}
            return PV.bagla(out, lambda: K.for_live(out, 'denetim.hareket', 'Logo muhasebe hareketleri (hesap)', year,
                                                     logo_db(), 'Hesabın dönem içindeki iptal edilmemiş hareketleri: '
                                                     'borç ve alacak Logo\'daki tutardır; sayfa başına 50 satır.'))
        except HTTPException:
            raise
        except Exception:
            log.exception("Financial audit detail failed")
            raise HTTPException(503, "Logo hareketleri okunamadı.")

    # Bulgu açıklaması ve istisna kümeleme: bulgu kuraldır, Zeki AI yalnız açıklar/sınıflar (financial_audit_explain).
    from .financial_audit_explain import register as register_explain
    register_explain(app, runtime, authorize, query, load_run, archive_root)

    snapshots = AuditSnapshots(archive_root, build_report)
    snapshots.year = audit_years()[-1]  # arka plan raporu açılan en son yılın kopyasından
    return snapshots
