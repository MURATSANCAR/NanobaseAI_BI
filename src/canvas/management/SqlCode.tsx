import { useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';

/**
 * SQL metni, renklendirilmiş. shiki yalnız bu bileşen ilk açıldığında ve yalnız SQL dili + tek tema
 * ile yüklenir; ana paket büyümez. Renklendirme gelene kadar düz metin gösterilir, metin hiç değişmez.
 */
type Highlighter = { codeToHtml: (code: string, opts: { lang: string; theme: string }) => string };
let highlighter: Promise<Highlighter> | null = null;

function loadHighlighter(): Promise<Highlighter> {
  highlighter ??= (async () => {
    const [{ createHighlighterCore }, { createJavaScriptRegexEngine }, sql, theme] = await Promise.all([
      import('shiki/core'),
      import('shiki/engine/javascript'),
      import('shiki/langs/sql.mjs'),
      import('shiki/themes/github-light.mjs'),
    ]);
    return createHighlighterCore({ langs: [sql.default], themes: [theme.default], engine: createJavaScriptRegexEngine() });
  })();
  return highlighter;
}

export default function SqlCode({ sql, label }: { sql: string; label: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [copied, setCopied] = useState<'ok' | 'fail' | null>(null);

  useEffect(() => {
    let alive = true;
    loadHighlighter()
      .then((h) => alive && setHtml(h.codeToHtml(sql, { lang: 'sql', theme: 'github-light' })))
      .catch(() => alive && setHtml(null));
    return () => {
      alive = false;
    };
  }, [sql]);

  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(null), 1600);
    return () => window.clearTimeout(t);
  }, [copied]);

  const copy = () =>
    navigator.clipboard.writeText(sql).then(
      () => setCopied('ok'),
      () => setCopied('fail'),
    );

  return (
    <div className="mg-sql">
      <div className="mg-sql-bar">
        <span>{sql.split('\n').length} satır</span>
        <button type="button" className="mg-sql-copy" onClick={copy} aria-label={`${label} SQL'ini kopyala`}>
          {copied === 'ok' ? <Check size={14} /> : <Copy size={14} />}
          {copied === 'ok' ? 'Kopyalandı' : copied === 'fail' ? 'Kopyalanamadı' : 'Kopyala'}
        </button>
      </div>
      {html ? (
        // shiki çıktısı yalnız kendi ürettiği span'lardan oluşur; SQL metni kaçışlanmış gelir.
        <div className="mg-sql-code" tabIndex={0} dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <pre className="mg-sql-code" tabIndex={0}>
          <code>{sql}</code>
        </pre>
      )}
    </div>
  );
}
