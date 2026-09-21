-- Why a page was sent to OCR, and whether its digital text can be trusted. A text layer
-- can be made of perfectly valid letters in a scrambled order (text set on a curve, a
-- broken export): "Osman farklıdeğildisanırım . Tab leti mi dabe nd en". Character-level
-- checks pass it; it went into the analysis as the page's text. The measurements that
-- expose it are kept per page so the decision can be audited.
SET search_path = ed, public;
ALTER TABLE page ADD COLUMN IF NOT EXISTS layer_health jsonb NOT NULL DEFAULT '{}';
