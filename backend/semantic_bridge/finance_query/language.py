"""Independent Turkish date/text primitives for the contract engine.

No imports from the legacy semantic parser, vocabulary or catalog.
"""
import re
import unicodedata
from datetime import date, timedelta
from calendar import monthrange
from .contracts import ContractError


def fold(text):
    value = str(text).translate(str.maketrans("İIıŞşĞğÜüÖöÇç", "iiiSsGgUuOoCc")).lower()
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).replace("’", "'")


UNITS = dict(zip("sifir bir iki uc dort bes alti yedi sekiz dokuz".split(), range(10)))
TENS = dict(zip("on yirmi otuz kirk elli altmis yetmis seksen doksan".split(), range(10, 100, 10)))


def normalize_numbers(text):
    """Normalize Turkish cardinal phrases, without changing non-number words."""
    words = "|".join([*UNITS, *TENS, "yuz", "bin", "milyon"])
    def convert(match):
        total = current = 0
        for word in match.group().split():
            if word in UNITS: current += UNITS[word]
            elif word in TENS: current += TENS[word]
            elif word == "yuz": current = (current or 1) * 100
            else:
                total += (current or 1) * (1000 if word == "bin" else 1000000)
                current = 0
        return str(total + current)
    return re.sub(r"\b(?:" + words + r")(?:\s+(?:" + words + r"))*\b", convert, fold(text))


def shift_month(d, offset):
    year, month = divmod(d.year * 12 + d.month - 1 + offset, 12)
    return date(year, month + 1, 1)


MONTHS = {n: i for i, n in enumerate("ocak subat mart nisan mayis haziran temmuz agustos eylul ekim kasim aralik".split(), 1)}


def next_month(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def dates(question, today):
    q = normalize_numbers(question)
    hits = []
    rolling_windows = []
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
        # Relative year belongs to the named month, not an additional whole-year period.
        month_suffix = r"(?:'?(?:da|de|ta|te|un|in|unda|inde))?"
        for m in re.finditer(r"\b(bu|gecen|onceki)\s+(?:yil\w*|sene\w*)\s+(" + month_names + r")" + month_suffix + r"\b", q):
            if free(m):
                year = today.year - int(m[1] != "bu")
                start = date(year, MONTHS[m[2]], 1); add(*m.span(), start, next_month(start))
        for m in re.finditer(r"\b(?:((?:20\d{2})|bu yil\w*|bu sene\w*)\s+)?ilk\s+(\d+)\s+ay\w*", q):
            if free(m):
                n = int(m[2])
                if not 1 <= n <= 12: raise ValueError()
                year = int(m[1]) if m[1] and m[1].isdigit() else today.year
                start = date(year, 1, 1); add(*m.span(), start, shift_month(start, n))
        quarter = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
        ordinals = {"birinci": 1, "ikinci": 2, "ucuncu": 3, "dorduncu": 4}
        year_phrase = r"(?:20\d{2}(?:'?(?:nin|in))?(?:\s+yil(?:in)?in)?|(?:bu|gecen|onceki)\s+(?:yilin|senenin))"
        ordinal = r"(?:birinci|ikinci|ucuncu|dorduncu|[1-4]\.?)"
        for m in re.finditer(r"\b(" + year_phrase + r")\s+(" + ordinal + r")\s+ceyre[kg]\w*", q):
            if not free(m): continue
            y = int(m[1][:4]) if m[1][:4].isdigit() else today.year - int(m[1].startswith(("gecen", "onceki")))
            n = ordinals[m[2]] if m[2] in ordinals else int(m[2].rstrip("."))
            start = date(y, (n-1)*3+1, 1)
            add(*m.span(), start, shift_month(start, 3))
        for m in re.finditer(r"\bson\s+(?:tamamlanan\s+)?(\d+)\s+(?:tamamlanmis\s+)?(?:(?:tam\s+)?takvim\s+)?(ay|gun|hafta|yil)\w*", q):
            if not free(m): continue
            n = int(m[1])
            rolling_windows.append(m.span())
            if not 1 <= n <= ({"ay": 120, "yil": 10, "hafta": 520, "gun": 3660}[m[2]]): raise ValueError()
            if m[2] in ("ay", "yil"):
                start = shift_month(today, -n * (12 if m[2] == "yil" else 1))
                if re.search(r"tamamlanan|tamamlanmis|tam takvim", m[0]):
                    if m[2] == "yil": start = date(today.year-n, 1, 1)
                    add(*m.span(), start, today.replace(month=1, day=1) if m[2] == "yil" else today.replace(day=1))
                else:
                    start = start.replace(day=min(today.day, monthrange(start.year, start.month)[1]))
                    add(*m.span(), start, today+timedelta(days=1))
            else:
                add(*m.span(), today-timedelta(days=n * (7 if m[2] == "hafta" else 1)-1), today+timedelta(days=1))
        for m in re.finditer(r"\b(?:onumuzdeki|gelecek)\s+(\d+)\s+(gun|hafta|ay|yil)\w*", q):
            if not free(m): continue
            n = int(m[1])
            if not 1 <= n <= {"gun": 3660, "hafta": 520, "ay": 120, "yil": 10}[m[2]]: raise ValueError()
            if m[2] in ("ay", "yil"):
                end = shift_month(today, n*(12 if m[2] == "yil" else 1))
                end = end.replace(day=min(today.day, monthrange(end.year,end.month)[1]))
            else: end = today+timedelta(days=n*(7 if m[2] == "hafta" else 1))
            add(*m.span(), today, end)
        for m in re.finditer(r"\b(\d+)\s+hafta\s+icinde\b", q):
            if free(m):
                n = int(m[1])
                if not 1 <= n <= 520: raise ValueError()
                add(*m.span(), today, today+timedelta(days=n*7))
        for m in re.finditer(r"\b(" + month_names + r")" + month_suffix + r"\b", q):
            if free(m):
                start = date(today.year, MONTHS[m[1]], 1); add(*m.span(), start, next_month(start))
        for m in re.finditer(r"\b(?:yilbasindan|sene basindan|bu yilin basindan)\s+(?:bugune|simdiye)(?:\s+kadar)?", q):
            if free(m): add(*m.span(), date(today.year, 1, 1), today+timedelta(days=1))
        relatives = [
            (r"\bbu ceyre[kg]\w*", quarter, shift_month(quarter, 3)),
            (r"\b(?:gecen|onceki) ceyre[kg]\w*", shift_month(quarter, -3), quarter),
            (r"\b(bugun(?:un|ku|de)?)\b", today, today+timedelta(days=1)),
            (r"\b(dun(?:ku|un)?|1 onceki gun\w*|1 onceki gune\w*)\b", today-timedelta(days=1), today),
            (r"\b(bu ay\w*)", today.replace(day=1), next_month(today)),
            (r"\b(onumuzdeki ay\w*|gelecek ay\w*)", next_month(today.replace(day=1)), shift_month(today, 2)),
            (r"\b(gecen ay\w*|onceki ay\w*)", (today.replace(day=1)-timedelta(days=1)).replace(day=1), today.replace(day=1)),
            (r"\b(bu yil\w*|bu sene\w*)", date(today.year,1,1), date(today.year+1,1,1)),
            (r"\b(gecen yil\w*|onceki yil\w*)", date(today.year-1,1,1), date(today.year,1,1)),
        ]
        for pattern, a, b in relatives:
            for m in re.finditer(pattern,q):
                if m.group().startswith("bugun") and rolling_windows and re.match(r"\s*(?:de\s+)?dahil\b", q[m.end():]):
                    continue  # inclusion qualifier of the rolling interval, not another period
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
    # "Each month's first N days" clips full month windows without adding a period.
    first_days = re.search(r"\bilk\s+(\d+)\s+gun\w*", q)
    # "Highest-selling first N days" is a ranking, not the month's opening
    # calendar days. Explicit possessive calendar scope wins when both occur.
    calendar_first_days = bool(first_days and re.search(
        r"(?:ayin|ayinin|aylarin|aylarinin|her ayin)\s*$", q[:first_days.start()]))
    ranked_days = bool(re.search(r"\b(?:en\s+(?:yuksek|dusuk|cok|az)|azalan|artan|sirala\w*)\b", q))
    if first_days and (calendar_first_days or not ranked_days):
        n = int(first_days[1])
        if not 1 <= n <= 31:
            raise ContractError("Ayın ilk günleri 1 ile 31 arasında olmalıdır.", code="NEEDS_CLARIFICATION")
        hits = [(a,b,lo,min(hi,lo+timedelta(days=n))) if lo.day == 1 and hi == next_month(lo) else (a,b,lo,hi) for a,b,lo,hi in hits]
    hits.sort()
    # Explicit inclusive/exclusive endpoints are a single interval, independent
    # of prose such as "dönemde" or "aralıkta". Never add the excluded end day.
    bounded_hits = []
    index = 0
    while index < len(hits):
        left = hits[index]
        if index + 1 < len(hits):
            right = hits[index + 1]
            left_marker = re.fullmatch(r"\s*(dahil|haric)\s*(?:(?:ile|ve)|[-–,;])?\s*", q[left[1]:right[0]])
            right_marker = re.match(r"\s*(dahil|haric)\b", q[right[1]:])
            if left_marker and right_marker and left[3]-left[2] == timedelta(days=1) and right[3]-right[2] == timedelta(days=1):
                lo = left[2] + (timedelta(days=1) if left_marker[1] == "haric" else timedelta(0))
                hi = right[2] + (timedelta(days=1) if right_marker[1] == "dahil" else timedelta(0))
                if lo >= hi:
                    raise ContractError("Açık tarih aralığının başlangıcı bitişinden önce olmalı.", code="NEEDS_CLARIFICATION")
                bounded_hits.append((left[0], right[1]+right_marker.end(), lo, hi))
                index += 2
                continue
        bounded_hits.append(left)
        index += 1
    hits = bounded_hits
    for i, (a,b,lo,hi) in enumerate(hits):
        if re.search(r"(?:gecen|onceki) yil\w*\s+ayni\s+(?:aralik|aralig|donem|ay)", q[a:]) and lo == date(today.year-1,1,1) and hi == date(today.year,1,1):
            anchors = [h for j,h in enumerate(hits) if j != i and h[2].year == today.year]
            if anchors:
                base = anchors[0]
                def previous_year(d): return d.replace(year=d.year-1, day=min(d.day, monthrange(d.year-1,d.month)[1]))
                hits[i] = (a,b,previous_year(base[2]),previous_year(base[3]))
    if len(hits)==2 and re.search(r"\barasi\w*|\baraligi\w*",q) and not re.search(r"karsilastir|gore|kiyas|ayni\s+(?:aralik|aralig|donem)",q):
        hits=[(hits[0][0],hits[1][1],hits[0][2],hits[1][3])]
    grain = next((g for g,p in [("month",r"\baylik\b|\bay ay\b|\bay(?:lar)? bazinda\b|\baylara gore\b"),("day",r"\bgunluk\b|\bgun gun\b|\bgun(?:ler)? bazinda\b|\bgunlere gore\b"),("year",r"\byillik\b|\byil yil\b|\byil(?:lar)? bazinda\b|\byillara gore\b")] if re.search(p,q)),None)
    return tuple(dict.fromkeys((str(a),str(b)) for _,_,a,b in hits)),grain
