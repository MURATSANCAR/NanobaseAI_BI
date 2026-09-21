import { useState } from 'react';
import { Copy, Code2 } from 'lucide-react';

export default function SqlEvidence({ sql, description, title = 'Bulgunun SQL sorgusu' }: { sql?: string | null; description: string; title?: string }) {
  const [message, setMessage] = useState('');
  if (!sql) return <p className="audit-sql-unavailable">Bu kayıtlı raporda sorgu bilgisi bulunmuyor.</p>;
  async function copy() {
    try { await navigator.clipboard.writeText(sql!); setMessage('Sorgu kopyalandı.'); }
    catch { setMessage('Kopyalama yapılamadı. Sorgu metnini seçerek kopyalayabilirsiniz.'); }
  }
  return <details className="audit-sql"><summary><Code2 size={16}/>{title}</summary><p>{description}</p><button className="audit-button" onClick={copy}><Copy size={14}/> SQL’i kopyala</button>{message && <p role="status">{message}</p>}<pre tabIndex={0} aria-label={title}><code>{sql}</code></pre></details>;
}
