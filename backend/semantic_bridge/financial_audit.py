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

from fastapi import HTTPException, Query, Request

log = logging.getLogger(__name__)
REVISION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def dec(value):
    return Decimal(str(value or 0))


def register(app, runtime, authorize):
    lock = threading.Lock()
    cache = {}

    @app.get("/api/v1/financial-audit/catalog")
    def catalog(request: Request):
        authorize(request)
        path = Path(__file__).resolve().parents[2] / 'configs/financial-audit/source.json'
        if not path.exists():
            raise HTTPException(503, 'Kontrol kaynağı bu kurulumda bulunamadı.')
        return json.loads(path.read_text(encoding='utf-8'))

    def context(year):
        # Only the declared, inspected current backup is enabled for this first version.
        # Older copies require opening/closing and source reconciliation before activation.
        if year != 2026:
            raise HTTPException(422, "Bu sürümde doğrulanan kaynak dönemi 2026'dır.")
        return (date(year, 1, 1), date(year + 1, 1, 1))

    def query(sql, year):
        r = runtime()
        result = r.run_sql(sql, 10000, context(year))
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
    def overview(request: Request, year: int = 2026):
        authorize(request)
        context(year)
        # A single bounded reader, shared by viewers. No duplicate heavy runs.
        with lock:
            import time
            if year in cache and time.time() - cache[year][0] < 120:
                return dict(cache[year][1], cached=True)
            try:
                sql = f"""SELECT A.LOGICALREF AS accountRef,A.CODE AS code,A.DEFINITION_ AS name,
                  A.ACCTYPE AS accountType, COUNT(*) AS lineCount,
                  SUM(CAST(L.DEBIT AS decimal(28,4))) AS debit,
                  SUM(CAST(L.CREDIT AS decimal(28,4))) AS credit,
                  SUM(CASE WHEN L.DEBIT IS NULL OR L.CREDIT IS NULL THEN 1 ELSE 0 END) AS nullAmounts,
                  SUM(CASE WHEN F.TRCODE=1 THEN 1 ELSE 0 END) AS openingLines,
                  MIN(L.DATE_) AS firstDate,MAX(L.DATE_) AS lastDate
                  {joins} WHERE {where(year)}
                  GROUP BY A.LOGICALREF,A.CODE,A.DEFINITION_,A.ACCTYPE ORDER BY A.CODE"""
                result = query(sql, year)
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
                slips = query(slip_sql, year)
                imbalance = slips["records"][0]
                integrity = query(f"""SELECT COUNT(*) AS sourceRows,
                  SUM(CASE WHEN F.LOGICALREF IS NULL THEN 1 ELSE 0 END) AS missingSlip,
                  SUM(CASE WHEN F.CANCELLED<>0 THEN 1 ELSE 0 END) AS cancelledSlip
                  FROM dbo.LG_411_01_EMFLINE L LEFT JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=L.ACCFICHEREF
                  WHERE L.DATE_ >= '{year}0101' AND L.DATE_ < '{year+1}0101' AND L.CANCELLED=0""", year)
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
                       "source": "Logo · 2026 işlem dönemi · 17.08.2026 yedeği", "currency": "TRY",
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
                cache[year] = (time.time(), out)
                return out
            except HTTPException:
                raise
            except Exception:
                log.exception("Financial audit could not read the source")
                raise HTTPException(503, "Logo verisi okunamadı. Denetim DOĞRULANAMADI; tekrar deneyin.")

    @app.get("/api/v1/financial-audit/lines")
    def lines(request: Request, year: int = 2026, account: int = Query(..., ge=1), page: int = Query(0, ge=0, le=100000)):
        authorize(request)
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
            return {"items": result['records'], "total": result['records'][0]['totalRows'] if result['records'] else 0,
                    "page": page, "readAt": datetime.now(timezone.utc).isoformat(), "dbMs": result.get('dbMs'),
                    "sql": result.get('physicalSql'), "separateRead": True}
        except HTTPException:
            raise
        except Exception:
            log.exception("Financial audit detail failed")
            raise HTTPException(503, "Logo hareketleri okunamadı.")
