"""Bind explicitly named physical context using configured placeholder labels."""
from semantic_layer.normalize import tokenize, is_inflection_of


def select_profiles(profiles, scope):
    return [p for p in profiles if all(k not in p.context or str(p.context[k]) == str(v) for k, v in scope.items())]


def extract_scope(question, labels, profiles):
    """Bind adjacent numeric literals; labels are source configuration, not generated meaning."""
    words = tokenize(question)
    scope, errors = {}, []
    for axis, label in enumerate(labels):
        name = tokenize(label)
        if len(name) != 1:
            continue
        positions = [i for i, w in enumerate(words) if is_inflection_of(w, name[0])]
        found = []
        for pos in positions:
            left = words[pos - 1] if pos else ''
            right = words[pos + 1] if pos + 1 < len(words) else ''
            number = left if left.isdigit() else right if right.isdigit() else None
            if number is None:
                continue
            around = words[max(0, pos - 3):pos + 4]
            if any(w in {'haric', 'haricindeki', 'disinda', 'disindaki', 'degil', 'except', 'excluding'} for w in around):
                errors.append(f'{label} kapsamındaki dışlama koşulu netleştirilmeli.')
                continue
            if pos >= 2 and words[pos - 2].isdigit():
                errors.append(f'{label} kapsamındaki sayı aralığı netleştirilmeli.')
                continue
            if pos >= 3 and words[pos - 2] in {'ve', 'veya', 'ile'} and words[pos - 3].isdigit():
                errors.append(f'{label} kapsamı birden çok değer içeriyor; tek kapsam belirtin.')
                continue
            if not left.isdigit() and pos + 3 < len(words) and right.isdigit() and words[pos + 2] in {'ve', 'veya', 'ile'} and words[pos + 3].isdigit():
                errors.append(f'{label} kapsamı birden çok değer içeriyor; tek kapsam belirtin.')
                continue
            found.append(number)
        if not found:
            continue
        if len(set(found)) != 1:
            errors.append(f'{label} kapsamındaki farklı değerler netleştirilmeli.')
            continue
        key, number = f'n{axis}', found[0]
        available = {str(p.context[key]) for p in profiles if key in p.context}
        matches = {number} if number in available else {v for v in available if v.isdigit() and int(v) == int(number)}
        if len(matches) != 1:
            errors.append(f'{label} {number} kapsamı bağlı katalogda tek bir değere karşılık gelmiyor.')
            continue
        scope[key] = next(iter(matches))
    return scope, list(dict.fromkeys(errors))


def execution_profiles(sql, profiles, scope, dialect):
    if not scope:
        return profiles
    from semantic_layer.runtime.guardrails import referenced_tables
    chosen = select_profiles(profiles, scope)
    allowed = {p.table_name.upper() for p in chosen}
    known = {p.table_name.upper(): p for p in profiles}
    for name in referenced_tables(sql, dialect):
        raw = name.split('.')[-1].strip('[]`"').upper()
        direct = raw if raw in known else next((k for k, p in known.items() if raw == f'{p.schema_name}_{k}'.upper()), None)
        if direct and direct not in allowed:
            raise ValueError('SQL tablosu istekteki fiziksel veri kapsamının dışında: ' + name)
    return chosen
