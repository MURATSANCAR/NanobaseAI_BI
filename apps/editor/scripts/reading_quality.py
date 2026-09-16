"""Conservative exact-quotation gate; agreement is not semantic verification."""
import re
import unicodedata


def normalized(text):
    text = re.sub(r'-\s*\n\s*', '', text)
    text = unicodedata.normalize('NFKC', text).replace('İ', 'i').replace('I', 'ı').lower()
    return ''.join(c for c in text if c.isalnum())


def assess_page_reading(caption, tesseract_text, paddle_lines):
    readers = {'tesseract': normalized(tesseract_text),
               'paddle': normalized('\n'.join(r['text'] for r in paddle_lines))}
    quotes = re.findall(r'["“]([^"”\n]{12,})["”]', caption)
    checks = []
    for quote in quotes:
        text = normalized(quote)
        supporters = [name for name, full in readers.items() if text and text in full]
        checks.append({'quote': quote, 'readers_with_normalized_text': supporters,
                       'status': 'TEXT_MATCH_ONLY' if supporters else 'UNSUPPORTED_QUOTE'})
    blocked = any(c['status'] == 'UNSUPPORTED_QUOTE' for c in checks)
    return {'quote_checks': checks,
            'caption_status': 'BLOCKED_QUOTE_MISMATCH' if blocked else 'UNVERIFIED_CANDIDATE',
            'allow_as_verified_fact': False,
            'scope': 'Normalized quoted text only; punctuation/case ignored; does not verify speaker, event or illustration',
            'reading_disagreements': sum(r.get('reading_agrees') is False for r in paddle_lines)}
