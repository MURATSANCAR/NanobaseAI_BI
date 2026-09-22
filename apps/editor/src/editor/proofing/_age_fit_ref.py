"""What books published for an age band actually look like (reference for age_fit).

Measured 2026-09-22 on the publisher's corpus on the GPU host (/data/organized): every PDF's
text layer rebuilt into paragraphs by the pipeline's own document.paragraphs_from_layout
(the same builder that makes an analysed book's text — measured on the six analysed books,
the two paths agree within 2.2 Ateşman points), the band printed in the book itself, the
same measure code as the check (_age_fit_text). Books with >= 300 words: 288 printed "6-10 yaş" (or 7-9), 5 printed
"4-5 yaş", 33 adult novels (kurgu, no band). Percentiles are BOOK-WEIGHTED (every book
counts once, however many pages it has), so a few long books cannot set the reference.

Only a band with >= 30 books gets a reference. A declared band inside a referenced band
(7-9 inside 6-10) uses it; any other band gets book-level measures only, no page or
sentence warnings: there is nothing measured to compare it with. The corpus is text-layer
extraction, so its extremes include layout artefacts (unpunctuated lists, poems): the
thresholds below are therefore conservative (they fire less, not more).

How well the formulas separate bands at book level (AUC, 288 books 6-10 vs 33 adult
novels): Ateşman 0.73, Çetinkaya–Uzun 0.73, words/sentence 0.70, Bezirci–Yılmaz 0.70,
long-word share 0.57. A formula is therefore never a verdict on a book; only outlier
sentences and pages become warnings.
"""
from __future__ import annotations

REFERENCE: dict[str, dict] = {
    "6-10": {
        "band": (6, 10),
        "books": 288,
        # sentence length in words, book-weighted: p50 6, p90 11, p99 24, p99.5 39, p99.9 98
        # (adult novels: p50 6, p90 14, p99 24, p99.5 28). Beyond p99 the 6-10 tail is
        # extraction artefacts (an unpunctuated list or poem), so p99 is the limit: a
        # sentence longer than 99 of 100 sentences in books for this band — and in novels.
        "sentence_words_p50": 6,
        "sentence_words_p99": 24,
        # pages with >= 3 sentences (one or two sentences give no rate), book-weighted over
        # 14,051 pages: Ateşman p1 42.5, Bezirci–Yılmaz p99 18.63, words/sentence p99 15.67.
        "page_min_sentences": 3,
        "page_atesman_p1": 42.5,
        "page_yod_p99": 18.63,
        "page_asl_p99": 15.67,
        # book-level percentile tables (pct, value) over the 288 books
        "book_pct": {
            "atesman": [(1, 23.1), (5, 70.5), (10, 72.1), (25, 75.4), (50, 80.1), (75, 83.8), (90, 86.6),
                        (95, 88.6), (99, 114.4)],
            "cetinkaya": [(1, 33.8), (5, 41.0), (10, 42.6), (25, 44.1), (50, 46.5), (75, 48.8), (90, 50.6),
                          (95, 52.3), (99, 70.0)],
            "yod": [(1, 3.38), (5, 4.74), (10, 5.03), (25, 5.53), (50, 6.34), (75, 7.35), (90, 8.63), (95, 9.49),
                    (99, 20.33)],
            "asl": [(1, 4.95), (5, 5.21), (10, 5.4), (25, 5.79), (50, 6.28), (75, 6.96), (90, 8.18), (95, 8.99),
                    (99, 37.67)],
        },
    },
}


def reference_for(band: tuple[int, int] | None) -> tuple[str | None, dict | None]:
    """The measured band that contains the declared one (narrowest first), else none."""
    if band is None:
        return None, None
    fits = [(r["band"][1] - r["band"][0], k, r) for k, r in REFERENCE.items()
            if r["band"][0] <= band[0] and band[1] <= r["band"][1]]
    if not fits:
        return None, None
    _, k, r = min(fits)
    return k, r
