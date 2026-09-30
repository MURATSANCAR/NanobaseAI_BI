"""Independent Turkish date/text primitives for the contract engine.

No imports from the legacy semantic parser, vocabulary or catalog.
"""
import re
import unicodedata
from datetime import date, timedelta
from .contracts import ContractError


def fold(text):
    value = str(text).translate(str.maketrans("İIıŞşĞğÜüÖöÇç", "iiiSsGgUuOoCc")).lower()
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).replace("’", "'")


MONTHS = {n: i for i, n in enumerate("ocak subat mart nisan mayis haziran temmuz agustos eylul ekim kasim aralik".split(), 1)}


def next_month(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def dates(question, today):
    q = fold(question)
    hits = []
    def add(a, b, lo, hi):
        if lo >= hi:
            raise ContractError("Tarih aralığının başlangıcı bitişinden önce olmalı.")
        hits.append((a, b, lo, hi))
    month_names = "|".join(MONTHS)
    try:
        for m in re.finditer(r"\b(\d{1,2})\s+(" + month_names + r")\s+(20\d{2})\b", q):
            d = date(int(m[3]), MONTHS[m[2]], int(m[1])); add(*m.span(), d, d + timedelta(days=1))
        for m in re.finditer(r"\b(20\d{2})-(\d{2})-(\d{2})\b", q):
            d = date(int(m[1]), int(m[2]), int(m[3])); add(*m.span(), d, d + timedelta(days=1))
        for m in re.finditer(r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b", q):
            d = date(int(m[3]), int(m[2]), int(m[1])); add(*m.span(), d, d + timedelta(days=1))
        def free(m):
            return not any(m.start() < b and a < m.end() for a,b,_,_ in hits)
        for m in re.finditer(r"\b(" + month_names + r")\s+(20\d{2})\b", q):
            if free(m):
                d = date(int(m[2]), MONTHS[m[1]], 1); add(*m.span(), d, next_month(d))
        for m in re.finditer(r"\b(20\d{2})\s+(" + month_names + r")\b", q):
            if free(m):
                d = date(int(m[1]), MONTHS[m[2]], 1); add(*m.span(), d, next_month(d))
        relatives = [
            (r"\b(bugun\w*)", today, today+timedelta(days=1)),
            (r"\b(dun|bir onceki gun\w*|bir onceki gune\w*)\b", today-timedelta(days=1), today),
            (r"\b(bu ay\w*)", today.replace(day=1), next_month(today)),
            (r"\b(gecen ay\w*|onceki ay\w*)", (today.replace(day=1)-timedelta(days=1)).replace(day=1), today.replace(day=1)),
            (r"\b(bu yil\w*|bu sene\w*)", date(today.year,1,1), date(today.year+1,1,1)),
            (r"\b(gecen yil\w*|onceki yil\w*)", date(today.year-1,1,1), date(today.year,1,1)),
        ]
        for pattern, a, b in relatives:
            for m in re.finditer(pattern,q):
                if free(m): add(*m.span(),a,b)
        for m in re.finditer(r"\bson\s+(\d+)\s+gun\w*",q):
            if free(m):
                n=int(m[1])
                if not 1<=n<=3660:raise ValueError()
                add(*m.span(),today-timedelta(days=n-1),today+timedelta(days=1))
        for m in re.finditer(r"\b20\d{2}\b",q):
            if free(m):
                y=int(m[0]);add(*m.span(),date(y,1,1),date(y+1,1,1))
    except ValueError:
        raise ContractError("Tarih geçerli değil; gün, ay ve yılı kontrol edin.") from None
    hits.sort()
    if len(hits)==2 and re.search(r"\barasi\w*|\baraligi\w*",q):
        hits=[(hits[0][0],hits[1][1],hits[0][2],hits[1][3])]
    grain = next((g for g,p in [("month",r"\baylik\b|\bay ay\b|\bay(?:lar)? bazinda\b"),("day",r"\bgunluk\b|\bgun bazinda\b"),("year",r"\byil(?:lar)? bazinda\b")] if re.search(p,q)),None)
    return tuple(dict.fromkeys((str(a),str(b)) for _,_,a,b in hits)),grain
