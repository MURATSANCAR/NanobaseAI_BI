"""Geometry-only reader alignment. Never search for a matching answer in the text."""
import math
import unicodedata


def corrupt_character(character):
    """All Unicode private-use planes, surrogates and replacement characters.

    Historical artifacts checked only BMP private-use code points. Re-evaluate
    actual words on read so those immutable artifacts never become authorities.
    """
    return unicodedata.category(character) in ('Co', 'Cs') or character == '\ufffd'


def valid_box(box):
    return (isinstance(box, (list, tuple)) and len(box) == 4
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in box)
            and min(box) >= 0 and box[2] > 0 and box[3] > 0
            and box[0] + box[2] <= 1.001 and box[1] + box[3] <= 1.001)


def aligned_words(box, lines):
    """Select spatially covered words, not their entire containing PDF/OCR line.

    Half-word overlap is insufficient when the word centre falls outside the
    detected region. This deliberately leaves ambiguous fragments unresolved.
    Line order and word order come from the independent reader, never OCR text.
    """
    if not valid_box(box):
        raise ValueError('INVALID_SOURCE_BOX')
    x, y, w, h = box
    selected = []
    for line_index, line in enumerate(lines):
        words = line.get('words', [])
        for word_index, word in enumerate(words):
            wb = word.get('bbox')
            if not valid_box(wb):
                continue
            wx, wy, ww, wh = wb
            overlap_x = max(0, min(x+w, wx+ww)-max(x, wx)) / ww
            overlap_y = max(0, min(y+h, wy+wh)-max(y, wy)) / min(h, wh)
            if (x-.002 <= wx+ww/2 <= x+w+.002
                    and y-.004 <= wy+wh/2 <= y+h+.004
                    and overlap_x >= .5 and overlap_y >= .5):
                selected.append({**word, 'line_index': line_index,
                                 'word_index': word_index,
                                 'corrupt_private_unicode': line.get('corrupt_private_unicode', False)
                                 or any(corrupt_character(c) for c in word.get('text', ''))})
    # Explicitly retain positions so independent checks can reproduce selection.
    return selected


def reader_text(box, lines):
    words = aligned_words(box, lines)
    text = ' '.join(word['text'] for word in words)
    usable = bool(words) and not any(word['corrupt_private_unicode'] for word in words)
    return text, words, usable


def reading_order(rows):
    """Group overlapping text baselines before sorting left-to-right.

    Detector output order can put the last word of a slightly tilted line first.
    Keep this geometric order explicit; multi-column narrative order still needs
    layout review and is not inferred from the content of the words.
    """
    lines = []
    for row in sorted(rows, key=lambda r: (r['data']['bbox'][1], r['data']['bbox'][0])):
        x, y, w, h = row['data']['bbox']
        compatible = []
        for i, line in enumerate(lines):
            ly, lh = line['y'], line['h']
            overlap = max(0, min(y+h, ly+lh)-max(y, ly)) / min(h, lh)
            distance = abs(y+h/2-ly-lh/2)
            if overlap >= .5 and distance <= .6*max(h, lh):
                compatible.append((distance, i))
        if compatible:
            lines[min(compatible)[1]]['rows'].append(row)
        else:
            lines.append({'y': y, 'h': h, 'rows': [row]})
    return [row for line in lines for row in sorted(line['rows'], key=lambda r:r['data']['bbox'][0])]
