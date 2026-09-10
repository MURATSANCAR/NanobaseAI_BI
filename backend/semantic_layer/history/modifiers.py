"""Conservative, offline semantic-equivalence evidence from human-reviewed pairs.

Both the original question and its modifier-free control must have independent
approval and the same SQL AST. Comparing two outputs of our own resolver would
be circular. Exact question matching deliberately avoids generalising direction,
negation, periods or entities from a superficially similar historical question.
"""
from collections import defaultdict

import sqlglot

from semantic_layer.normalize import tokenize


class ModifierHistory:
    def __init__(self, pairs, datasource_id):
        self.questions = defaultdict(list)
        for pair in pairs:
            if not pair.human_verified or pair.source == "seed":
                continue
            if pair.datasource_id not in (None, datasource_id):
                continue
            try:
                statements = sqlglot.parse(pair.sql)
                if len(statements) != 1 or not isinstance(statements[0], sqlglot.exp.Query):
                    continue
                canonical = statements[0].sql()
            except (sqlglot.errors.ParseError, ValueError):
                continue
            self.questions[tuple(tokenize(pair.nl))].append((pair.id, canonical))

    def lookup(self, tokens, position):
        original = self.questions.get(tuple(tokens), [])
        control = self.questions.get(tuple(tokens[:position] + tokens[position + 1:]), [])
        if not original or not control:
            return []
        # Contradictory approvals invalidate the proof rather than cherry-picking.
        if len({sql for _, sql in original + control}) != 1:
            return []
        return sorted({pid for pid, _ in original + control})
