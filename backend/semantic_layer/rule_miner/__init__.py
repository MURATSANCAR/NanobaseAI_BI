"""Business rules mined from what the business already wrote down.

Logo's consultant views (AA_, EOS_, NY_, KPMG_…) and the CRM's saved views (FetchXML) carry the
company's own definitions: which TRCODE is a sale, what a "borç" is, which status means "YK onayında
bekleyen". Each becomes a candidate concept with the view as evidence, is refuted against the live
database, and is certified or queued for approval by the policy in `probe.decide`.
"""
